"""Tests for framework.health.preflight.

The point of preflight is to turn the cryptic Appium/UiAutomator2 dead-end (a
server with no ANDROID_HOME) into an actionable diagnosis. These exercise SDK
resolution against a fake SDK tree in tmp_path, the env self-heal, the Appium
status probe over a stubbed HTTP seam, driver-list parsing, and the aggregate
``preflight`` decisions — all without a real Appium/adb/HTTP dependency.
"""

import framework.health.preflight as pf
from framework.health.preflight import (
    PreflightResult,
    appium_status,
    driver_manager_healthy,
    driver_manager_remediation,
    ensure_android_home,
    installed_appium_drivers,
    node_npm_versions,
    preflight,
    required_driver,
    resolve_android_home,
)


def _fake_sdk(root):
    """Create a minimal SDK tree (platform-tools/adb) under ``root`` and return it."""
    tools = root / "platform-tools"
    tools.mkdir(parents=True)
    (tools / "adb").write_text("#!/bin/sh\n")
    return root


# --- resolve_android_home ---------------------------------------------------


def test_resolve_honours_valid_android_home(tmp_path, monkeypatch):
    sdk = _fake_sdk(tmp_path / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    assert resolve_android_home() == str(sdk)


def test_resolve_ignores_env_pointing_at_a_non_sdk(tmp_path, monkeypatch):
    """An ANDROID_HOME without platform-tools/adb is not accepted; probing wins."""
    empty = tmp_path / "not-an-sdk"
    empty.mkdir()
    monkeypatch.setenv("ANDROID_HOME", str(empty))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(pf, "_candidate_sdk_dirs", lambda: [])
    assert resolve_android_home() is None


def test_resolve_probes_common_location(tmp_path, monkeypatch):
    sdk = _fake_sdk(tmp_path / "Library" / "Android" / "sdk")
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(pf, "_candidate_sdk_dirs", lambda: [tmp_path / "nope", sdk])
    assert resolve_android_home() == str(sdk)


def test_resolve_returns_none_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(pf, "_candidate_sdk_dirs", lambda: [tmp_path / "absent"])
    assert resolve_android_home() is None


# --- ensure_android_home ----------------------------------------------------


def test_ensure_injects_both_vars_when_unset(tmp_path, monkeypatch):
    sdk = _fake_sdk(tmp_path / "sdk")
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(pf, "resolve_android_home", lambda: str(sdk))
    assert ensure_android_home() == str(sdk)
    import os

    assert os.environ["ANDROID_HOME"] == str(sdk)
    assert os.environ["ANDROID_SDK_ROOT"] == str(sdk)


def test_ensure_is_a_noop_when_already_set_to_a_real_sdk(tmp_path, monkeypatch):
    import os

    sdk = _fake_sdk(tmp_path / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    assert ensure_android_home() == str(sdk)
    assert "ANDROID_SDK_ROOT" not in os.environ  # a valid env is left untouched


def test_ensure_replaces_a_broken_android_home(tmp_path, monkeypatch):
    """A set-but-broken SDK path (moved/deleted SDK) must not be trusted: it looks
    configured while UiAutomator2 dies on it."""
    import os

    broken = tmp_path / "moved-sdk"
    broken.mkdir()
    sdk = _fake_sdk(tmp_path / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(broken))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(pf, "_candidate_sdk_dirs", lambda: [sdk])

    assert ensure_android_home() == str(sdk)
    assert os.environ["ANDROID_HOME"] == str(sdk)
    assert os.environ["ANDROID_SDK_ROOT"] == str(sdk)


def test_ensure_returns_none_when_unset_and_undetectable(monkeypatch):
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(pf, "resolve_android_home", lambda: None)
    assert ensure_android_home() is None


# --- appium_status ----------------------------------------------------------


class _Resp:
    def __init__(self, status_code, payload=None, raise_json=False):
        self.status_code = status_code
        self._payload = payload
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._payload


def test_appium_status_reachable_with_version(monkeypatch):
    payload = {"value": {"build": {"version": "2.11.0"}}}
    monkeypatch.setattr(pf.requests, "get", lambda url, timeout: _Resp(200, payload))
    reachable, version = appium_status("http://localhost:4723")
    assert reachable is True
    assert version == "2.11.0"


def test_appium_status_reachable_without_version(monkeypatch):
    monkeypatch.setattr(pf.requests, "get", lambda url, timeout: _Resp(200, {"value": {}}))
    assert appium_status("http://localhost:4723/") == (True, None)


def test_appium_status_unreachable_on_exception(monkeypatch):
    def _boom(url, timeout):
        raise pf.requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(pf.requests, "get", _boom)
    assert appium_status("http://localhost:4723") == (False, None)


def test_appium_status_non_200_is_unreachable(monkeypatch):
    monkeypatch.setattr(pf.requests, "get", lambda url, timeout: _Resp(500, {}))
    assert appium_status("http://localhost:4723") == (False, None)


# --- installed_appium_drivers -----------------------------------------------


def test_driver_list_parses_json(monkeypatch):
    class _P:
        stdout = '{"uiautomator2": {"version": "2.34.1", "installed": true}}'
        stderr = ""

    monkeypatch.setattr(pf.subprocess, "run", lambda *a, **k: _P())
    assert installed_appium_drivers() == {"uiautomator2": "2.34.1"}


def test_driver_list_parses_text_form(monkeypatch):
    class _P:
        stdout = ""
        stderr = "- uiautomator2@2.34.1 [installed (npm)]\n- xcuitest@7.0.0 [installed (npm)]"

    monkeypatch.setattr(pf.subprocess, "run", lambda *a, **k: _P())
    assert installed_appium_drivers() == {"uiautomator2": "2.34.1", "xcuitest": "7.0.0"}


def test_driver_list_empty_on_failure(monkeypatch):
    def _boom(*a, **k):
        raise OSError("appium not found")

    monkeypatch.setattr(pf.subprocess, "run", _boom)
    assert installed_appium_drivers() == {}


# --- node_npm_versions ------------------------------------------------------


def test_node_npm_versions_reads_both(monkeypatch):
    class _P:
        returncode = 0

        def __init__(self, out):
            self.stdout = out
            self.stderr = ""

    def _run(cmd, **kwargs):
        return _P("v20.11.0" if cmd[0] == "node" else "10.2.4")

    monkeypatch.setattr(pf.subprocess, "run", _run)
    assert node_npm_versions() == ("v20.11.0", "10.2.4")


def test_node_npm_versions_none_when_absent(monkeypatch):
    def _boom(cmd, **kwargs):
        raise OSError("not found")

    monkeypatch.setattr(pf.subprocess, "run", _boom)
    assert node_npm_versions() == (None, None)


def test_node_npm_versions_none_on_nonzero_exit(monkeypatch):
    class _P:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(pf.subprocess, "run", lambda *a, **k: _P())
    assert node_npm_versions() == (None, None)


# --- driver_manager_healthy -------------------------------------------------


def test_driver_manager_healthy_for_npm_10_node_20():
    ok, reason = driver_manager_healthy(lambda: ("v20.11.0", "10.2.4"))
    assert ok is True and reason is None


def test_driver_manager_unhealthy_for_npm_11_node_25():
    ok, reason = driver_manager_healthy(lambda: ("v25.0.0", "11.0.0"))
    assert ok is False
    assert reason is not None
    assert "11.0.0" in reason and "25.0.0" in reason


def test_driver_manager_unhealthy_from_node_major_alone():
    """Node >= 23 implies npm >= 11 even when npm itself can't be read."""
    ok, reason = driver_manager_healthy(lambda: ("v23.1.0", None))
    assert ok is False and reason is not None


def test_driver_manager_none_versions_treated_healthy():
    """Can't diagnose without versions — don't cry wolf."""
    ok, reason = driver_manager_healthy(lambda: (None, None))
    assert ok is True and reason is None


def test_driver_manager_remediation_names_versions_and_fix():
    text = driver_manager_remediation("v25.0.0", "11.0.0")
    assert "v25.0.0" in text and "11.0.0" in text
    # The verified, non-destructive fix: update by reinstalling the driver.
    assert "appium driver uninstall" in text and "appium driver install" in text
    # Not the old destructive advice.
    assert "nvm install --lts" not in text
    assert "npm <= 10" not in text


# --- required_driver --------------------------------------------------------


def test_required_driver_maps_platforms():
    assert required_driver("android") == "uiautomator2"
    assert required_driver("ios") == "xcuitest"
    assert required_driver("iOS") == "xcuitest"


# --- preflight --------------------------------------------------------------


def test_preflight_flags_missing_android_home_for_android_appium(monkeypatch):
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(pf, "resolve_android_home", lambda: None)
    monkeypatch.setattr(pf, "appium_status", lambda server: (False, None))
    monkeypatch.setattr(pf, "installed_appium_drivers", lambda: {})

    results = preflight("android", "appium", "http://localhost:4723")
    assert all(isinstance(r, PreflightResult) for r in results)

    android_home = next(r for r in results if r.name == "ANDROID_HOME")
    assert android_home.level == "fail" and not android_home.ok

    # android+appium needs a server and the uiautomator2 driver too.
    assert any(r.name == "Appium server" and r.level == "fail" for r in results)
    driver_check = next(r for r in results if r.name.startswith("Appium driver"))
    assert "uiautomator2" in driver_check.name and driver_check.level == "warn"


def test_preflight_all_green_for_android_appium(tmp_path, monkeypatch):
    sdk = _fake_sdk(tmp_path / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    monkeypatch.setenv("ANDROID_SDK_ROOT", str(sdk))
    monkeypatch.setattr(pf, "appium_status", lambda server: (True, "2.11.0"))
    monkeypatch.setattr(pf, "installed_appium_drivers", lambda: {"uiautomator2": "2.34.1"})

    results = preflight("android", "appium", "http://localhost:4723")
    assert all(r.level == "pass" for r in results)
    assert {r.name for r in results} == {
        "ANDROID_HOME",
        "Appium server",
        "Appium driver: uiautomator2",
    }


def test_preflight_android_adb_skips_server_checks(tmp_path, monkeypatch):
    """The adb backend needs no Appium server — only the ANDROID_HOME check applies."""
    sdk = _fake_sdk(tmp_path / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    monkeypatch.setenv("ANDROID_SDK_ROOT", str(sdk))
    results = preflight("android", "adb", "http://localhost:4723")
    assert [r.name for r in results] == ["ANDROID_HOME"]


def test_preflight_warns_when_android_home_points_at_a_non_sdk(tmp_path, monkeypatch):
    """A stale ANDROID_HOME (SDK moved) must not pass: it is reported, with the
    real SDK found on disk as the fix."""
    broken = tmp_path / "moved-sdk"
    broken.mkdir()
    sdk = _fake_sdk(tmp_path / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(broken))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(pf, "_candidate_sdk_dirs", lambda: [sdk])

    result = next(r for r in preflight("android", "adb", "http://localhost:4723") if r.name == "ANDROID_HOME")
    assert result.level == "warn"
    assert str(broken) in result.detail and str(sdk) in result.detail
    assert result.fix == f"export ANDROID_HOME={sdk}"


def test_preflight_fails_when_android_home_is_broken_and_nothing_detected(tmp_path, monkeypatch):
    broken = tmp_path / "moved-sdk"
    broken.mkdir()
    monkeypatch.setenv("ANDROID_HOME", str(broken))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(pf, "_candidate_sdk_dirs", lambda: [])

    result = next(r for r in preflight("android", "adb", "http://localhost:4723") if r.name == "ANDROID_HOME")
    assert result.level == "fail" and not result.ok
    assert str(broken) in result.detail


def test_preflight_ios_needs_no_android_home(monkeypatch):
    monkeypatch.setattr(pf, "appium_status", lambda server: (True, "2.11.0"))
    monkeypatch.setattr(pf, "installed_appium_drivers", lambda: {"xcuitest": "7.0.0"})
    results = preflight("ios", "appium", "http://localhost:4723")
    names = {r.name for r in results}
    assert "ANDROID_HOME" not in names
    assert "Appium driver: xcuitest" in names
