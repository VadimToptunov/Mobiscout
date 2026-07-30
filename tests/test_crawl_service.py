"""The crawl orchestration lives in a service layer so it can be tested without a
device or a terminal. These exercise driver selection, the foreground recovery,
and the full kit-writing path against fake drivers and a tmp output dir."""

import json

import pytest

from framework.cli.crawl_service import (
    CrawlServiceError,
    build_crawl_driver,
    ensure_foreground,
    preflight_or_raise,
    uninstall_app,
    write_kit,
)
from framework.crawler.app_crawler import AppCrawler
from framework.health.preflight import PreflightResult

_PKG = "com.example.app"


def _stub_preflight_pass(monkeypatch):
    """Neutralise the fail-fast preflight so a session-open test can reach the driver."""
    monkeypatch.setattr("framework.health.preflight.preflight", lambda *a, **k: [])


def _hierarchy(*nodes):
    return f'<?xml version="1.0"?><hierarchy rotation="0">{"".join(nodes)}</hierarchy>'


def _node(cls, text="", desc="", clickable=True, y=100):
    return (
        f'<node class="{cls}" text="{text}" content-desc="{desc}" resource-id="" '
        f'package="{_PKG}" clickable="{"true" if clickable else "false"}" '
        f'bounds="[0,{y}][200,{y + 80}]" />'
    )


_APP_SCREEN = _hierarchy(
    _node("android.widget.Button", "Transfer", desc="home.transfer", y=100),
    _node("android.widget.EditText", "", desc="home.amount", y=200),
)


class _FakeDriver:
    """A trivial driver that always shows the app's real screen in the foreground."""

    def __init__(self, package=_PKG):
        self._package = package

    def page_source(self):
        return _APP_SCREEN

    def tap(self, x, y):
        pass

    def back(self):
        pass

    def current_package(self):
        return self._package


# --- build_crawl_driver -----------------------------------------------------


def test_build_crawl_driver_adb_is_the_default_and_needs_no_session(monkeypatch):
    sentinel = object()
    captured = {}

    def _fake_adb(serial=None, launch_args=None):
        captured["serial"] = serial
        captured["launch_args"] = launch_args
        return sentinel

    monkeypatch.setattr("framework.crawler.AdbCrawlerDriver", _fake_adb)
    crawl_driver, appium_session = build_crawl_driver(
        package=_PKG,
        platform="android",
        driver="adb",
        serial=None,
        udid=None,
        device_name=None,
        server="http://localhost:4723",
        extra_caps={},
        launch_args=("--es", "K", "V"),
        app_activity=None,
    )
    assert crawl_driver is sentinel
    assert appium_session is None  # nothing to quit() for the adb path
    assert captured["launch_args"] == ["--es", "K", "V"]  # forwarded to the adb driver


def test_build_crawl_driver_ios_session_failure_raises_service_error(monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("framework.crawler.IOSCrawlerDriver", _boom)
    _stub_preflight_pass(monkeypatch)
    with pytest.raises(CrawlServiceError) as ei:
        build_crawl_driver(
            package=_PKG,
            platform="ios",
            driver="adb",
            serial=None,
            udid="UDID",
            device_name=None,
            server="http://localhost:4723",
            extra_caps={},
            launch_args=(),
            app_activity=None,
        )
    assert "Appium iOS session" in str(ei.value) and "connection refused" in str(ei.value)


def test_build_crawl_driver_appium_android_gives_actionable_android_home_message(monkeypatch):
    """When the underlying Appium error mentions ANDROID_HOME and we can detect an
    SDK, the raised message names the SDK path and the exact server restart fix."""

    def _boom(**kwargs):
        raise RuntimeError("UiAutomator2 failed: Neither ANDROID_HOME nor ANDROID_SDK_ROOT is set")

    monkeypatch.setattr("framework.crawler.AndroidAppiumDriver", _boom)
    monkeypatch.setattr("framework.health.preflight.ensure_android_home", lambda: None)
    monkeypatch.setattr("framework.health.preflight.resolve_android_home", lambda: "/opt/android/sdk")
    _stub_preflight_pass(monkeypatch)

    with pytest.raises(CrawlServiceError) as ei:
        build_crawl_driver(
            package=_PKG,
            platform="android",
            driver="appium",
            serial=None,
            udid="UDID",
            device_name=None,
            server="http://localhost:4723",
            extra_caps={},
            launch_args=(),
            app_activity=None,
        )
    msg = str(ei.value)
    assert "ANDROID_HOME=/opt/android/sdk" in msg
    assert "/opt/android/sdk" in msg
    assert "appium" in msg


def test_build_crawl_driver_appium_android_falls_back_to_generic_message(monkeypatch):
    """A genuine connectivity error (no ANDROID_HOME mention) keeps the generic hint."""

    def _boom(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("framework.crawler.AndroidAppiumDriver", _boom)
    monkeypatch.setattr("framework.health.preflight.ensure_android_home", lambda: None)
    _stub_preflight_pass(monkeypatch)

    with pytest.raises(CrawlServiceError) as ei:
        build_crawl_driver(
            package=_PKG,
            platform="android",
            driver="appium",
            serial=None,
            udid="UDID",
            device_name=None,
            server="http://localhost:4723",
            extra_caps={},
            launch_args=(),
            app_activity=None,
        )
    msg = str(ei.value)
    assert "Is the Appium server running" in msg
    assert "connection refused" in msg


def test_build_crawl_driver_appium_android_returns_the_session_to_quit(monkeypatch):
    sentinel = object()
    monkeypatch.setattr("framework.crawler.AndroidAppiumDriver", lambda **kwargs: sentinel)
    _stub_preflight_pass(monkeypatch)
    crawl_driver, appium_session = build_crawl_driver(
        package=_PKG,
        platform="android",
        driver="appium",
        serial=None,
        udid="UDID",
        device_name=None,
        server="http://localhost:4723",
        extra_caps={"deviceName": "x"},
        launch_args=(),
        app_activity=None,
    )
    assert crawl_driver is sentinel and appium_session is sentinel


# --- ensure_foreground ------------------------------------------------------


def test_ensure_foreground_when_already_foreground_does_not_launch():
    check = ensure_foreground(_FakeDriver(), _PKG, "android")
    assert check.ok and not check.launched and check.current == _PKG


class _LaunchableDriver:
    """Starts on a foreign package; ``launch`` brings the app forward."""

    def __init__(self):
        self._foreground = "com.other"
        self.launched = 0

    def current_package(self):
        return self._foreground

    def launch(self, package):
        self.launched += 1
        self._foreground = package
        return True


def test_ensure_foreground_launches_a_backgrounded_app():
    driver = _LaunchableDriver()
    check = ensure_foreground(driver, _PKG, "android")
    assert check.ok and check.launched and check.found == "com.other"
    assert driver.launched == 1


class _StuckDriver:
    """Never comes to the foreground and has no ``launch`` to try."""

    def current_package(self):
        return "com.other"


def test_ensure_foreground_gives_a_manual_hint_when_it_cannot_launch():
    android = ensure_foreground(_StuckDriver(), _PKG, "android")
    assert not android.ok and "adb shell monkey" in android.hint
    ios = ensure_foreground(_StuckDriver(), _PKG, "ios")
    assert not ios.ok and "simctl launch booted" in ios.hint


# --- write_kit --------------------------------------------------------------


@pytest.fixture()
def crawl_result():
    return AppCrawler(_FakeDriver(), _PKG, max_steps=10, max_depth=3).crawl()


def test_write_kit_writes_inventory_graph_and_tests(tmp_path, crawl_result):
    report = write_kit(
        result=crawl_result,
        output=str(tmp_path),
        package=_PKG,
        targets="python_pytest",
        style="flat",
        scaffold=False,
        server="http://localhost:4723",
        app_activity=None,
        launch_args=(),
    )
    assert (tmp_path / "inventory.md").exists()
    assert (tmp_path / "inventory.json").exists()
    assert (tmp_path / "graph.mmd").exists()
    assert (tmp_path / "graph.dot").exists()
    assert json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))  # valid JSON graph
    assert (tmp_path / "python_pytest").is_dir()
    assert not report.warnings
    assert any("Inventory" in line for line in report.info)


def test_write_kit_flags_an_unknown_target_without_aborting(tmp_path, crawl_result):
    report = write_kit(
        result=crawl_result,
        output=str(tmp_path),
        package=_PKG,
        targets="python_pytest,made_up_target",
        style="flat",
        scaffold=False,
        server="http://localhost:4723",
        app_activity=None,
        launch_args=(),
    )
    assert (tmp_path / "python_pytest").is_dir()  # the good target still ran
    assert any("made_up_target" in w for w in report.warnings)


def test_write_kit_scaffolds_a_runnable_project(tmp_path, crawl_result):
    report = write_kit(
        result=crawl_result,
        output=str(tmp_path),
        package=_PKG,
        targets="python_pytest",
        style="flat",
        scaffold=True,
        server="http://localhost:4723",
        app_activity=None,
        launch_args=(),
    )
    assert (tmp_path / "README.md").exists()
    assert any("Scaffolded" in line for line in report.info)


# --- preflight_or_raise (fail-fast before a session) ------------------------


def test_preflight_or_raise_raises_with_actionable_text_on_a_failure(monkeypatch):
    """A fail-level PreflightResult aborts with its detail and fix in the message."""
    monkeypatch.setattr(
        "framework.health.preflight.preflight",
        lambda *a, **k: [
            PreflightResult(
                "Appium server",
                False,
                "fail",
                "No Appium server reachable at http://localhost:4723",
                fix="Start Appium (e.g. `appium`) and retry",
            )
        ],
    )
    with pytest.raises(CrawlServiceError) as ei:
        preflight_or_raise("android", "appium", "http://localhost:4723")
    msg = str(ei.value)
    assert "No Appium server reachable" in msg
    assert "Start Appium" in msg


def test_preflight_or_raise_returns_warnings_and_does_not_block_when_all_ok(monkeypatch):
    """Warn-level results are returned (to be logged), not raised; passes are ignored."""
    monkeypatch.setattr(
        "framework.health.preflight.preflight",
        lambda *a, **k: [
            PreflightResult("ANDROID_HOME", True, "pass", "Android SDK at /sdk"),
            PreflightResult("Appium driver: uiautomator2", True, "warn", "not installed", fix="appium driver install"),
        ],
    )
    warnings = preflight_or_raise("android", "appium", "http://localhost:4723")
    assert any("not installed" in w for w in warnings)
    assert not any("Android SDK at /sdk" in w for w in warnings)  # passes are not warnings


def test_build_crawl_driver_runs_preflight_and_fails_fast(monkeypatch):
    """The appium path runs preflight FIRST; a fail aborts before the driver is built."""

    def _must_not_build(**kwargs):
        raise AssertionError("driver must not be built when preflight fails")

    monkeypatch.setattr("framework.crawler.AndroidAppiumDriver", _must_not_build)
    monkeypatch.setattr(
        "framework.health.preflight.preflight",
        lambda *a, **k: [PreflightResult("Appium server", False, "fail", "No Appium server reachable", fix="start it")],
    )
    with pytest.raises(CrawlServiceError) as ei:
        build_crawl_driver(
            package=_PKG,
            platform="android",
            driver="appium",
            serial=None,
            udid="UDID",
            device_name=None,
            server="http://localhost:4723",
            extra_caps={},
            launch_args=(),
            app_activity=None,
        )
    assert "No Appium server reachable" in str(ei.value)


def test_build_crawl_driver_adb_path_skips_preflight(monkeypatch):
    """The adb backend needs no server, so preflight must never run on that path."""

    def _boom_preflight(*a, **k):
        raise AssertionError("preflight must not run on the adb path")

    monkeypatch.setattr("framework.health.preflight.preflight", _boom_preflight)
    monkeypatch.setattr("framework.crawler.AdbCrawlerDriver", lambda serial=None, launch_args=None: object())
    crawl_driver, appium_session = build_crawl_driver(
        package=_PKG,
        platform="android",
        driver="adb",
        serial=None,
        udid=None,
        device_name=None,
        server="http://localhost:4723",
        extra_caps={},
        launch_args=(),
        app_activity=None,
    )
    assert appium_session is None


# --- uninstall_app ----------------------------------------------------------


def test_uninstall_app_android_uses_adb_with_serial(monkeypatch):
    captured = {}

    class _P:
        returncode = 0
        stdout = "Success\n"
        stderr = ""

    def _run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _P()

    monkeypatch.setattr("framework.cli.crawl_service.subprocess.run", _run)
    ok, message = uninstall_app(platform="android", package=_PKG, serial="ABC123", udid=None)
    assert ok
    assert captured["cmd"] == ["adb", "-s", "ABC123", "uninstall", _PKG]
    assert _PKG in message


def test_uninstall_app_ios_uses_simctl(monkeypatch):
    captured = {}

    class _P:
        returncode = 0
        stdout = ""
        stderr = ""

    def _run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _P()

    monkeypatch.setattr("framework.cli.crawl_service.subprocess.run", _run)
    ok, _ = uninstall_app(platform="ios", package="com.apple.Preferences", serial=None, udid="UDID-1")
    assert ok
    assert captured["cmd"] == ["xcrun", "simctl", "uninstall", "UDID-1", "com.apple.Preferences"]


def test_uninstall_app_failure_is_reported_not_raised(monkeypatch):
    """A non-zero exit (or adb's exit-0 "Failure" text) reports ok=False, never raises."""

    def _boom(cmd, **kwargs):
        raise OSError("adb not found")

    monkeypatch.setattr("framework.cli.crawl_service.subprocess.run", _boom)
    ok, message = uninstall_app(platform="android", package=_PKG, serial=None, udid=None)
    assert not ok
    assert "Could not uninstall" in message


def test_uninstall_app_android_exit_zero_failure_text_is_not_success(monkeypatch):
    class _P:
        returncode = 0
        stdout = "Failure [DELETE_FAILED_INTERNAL_ERROR]\n"
        stderr = ""

    monkeypatch.setattr("framework.cli.crawl_service.subprocess.run", lambda cmd, **k: _P())
    ok, _ = uninstall_app(platform="android", package=_PKG, serial=None, udid=None)
    assert not ok
