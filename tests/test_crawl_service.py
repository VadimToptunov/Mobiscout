"""The crawl orchestration lives in a service layer so it can be tested without a
device or a terminal. These exercise driver selection, the foreground recovery,
and the full kit-writing path against fake drivers and a tmp output dir."""

import json

import pytest

from framework.cli import crawl_service
from framework.cli.crawl_service import (
    CrawlServiceError,
    build_crawl_driver,
    ensure_foreground,
    write_kit,
)
from framework.crawler.app_crawler import AppCrawler

_PKG = "com.example.app"


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
    monkeypatch.setattr("framework.crawler.AdbCrawlerDriver", lambda serial=None: sentinel)
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
    assert crawl_driver is sentinel
    assert appium_session is None  # nothing to quit() for the adb path


def test_build_crawl_driver_ios_session_failure_raises_service_error(monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("framework.crawler.IOSCrawlerDriver", _boom)
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


def test_build_crawl_driver_appium_android_returns_the_session_to_quit(monkeypatch):
    sentinel = object()
    monkeypatch.setattr("framework.crawler.AndroidAppiumDriver", lambda **kwargs: sentinel)
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
    assert json.loads((tmp_path / "graph.json").read_text())  # valid JSON graph
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
