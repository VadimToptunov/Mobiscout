"""Environment detection: probe the automation toolchain with an injected runner,
so it's fully testable without the tools installed."""

import framework.health.environment as envmod
from framework.health.environment import Environment, detect_environment


def _runner(table):
    """A fake command runner: maps the first arg to a (code, output) response."""

    def run(cmd):
        return table.get(cmd[0], (127, ""))

    return run


def test_all_present_android_and_ios_ready():
    run = _runner(
        {
            "adb": (0, "Android Debug Bridge version 1.0.41"),
            "appium": (0, "2.11.3"),
            "java": (0, 'openjdk version "21.0.2"'),
            "xcrun": (0, "simctl help ..."),
        }
    )
    # appium driver list is a second call on "appium"; make it include both drivers.

    def run2(cmd):
        if cmd[:2] == ["appium", "driver"]:
            return (0, "- uiautomator2@3.0.0 [installed]\n- xcuitest@7.0.0 [installed]")
        return run(cmd)

    env = detect_environment(run=run2)
    assert isinstance(env, Environment)
    names = {t.name: t for t in env.tools}
    assert names["Appium"].found and names["Appium"].version == "2.11.3"
    assert names["Java (JDK)"].version == "21.0.2"
    assert set(env.appium_drivers) == {"uiautomator2", "xcuitest"}
    assert env.android_ready and env.ios_ready


def test_missing_tools_get_hints_and_not_ready():
    run = _runner({})  # nothing installed -> every probe returns 127
    env = detect_environment(run=run)
    by_name = {t.name: t for t in env.tools}
    assert not by_name["Appium"].found and "npm install -g appium" in by_name["Appium"].hint
    assert not by_name["adb (Android SDK)"].found
    assert not env.android_ready and not env.ios_ready
    assert env.appium_drivers == []


def test_android_ready_over_adb_without_appium():
    # Android only needs adb (crawls over adb, no Appium).
    env = detect_environment(run=_runner({"adb": (0, "Android Debug Bridge version 1.0.41")}))
    assert env.android_ready and not env.ios_ready


def test_daemon_environment_detect():
    from framework.cli.daemon_commands import JSONRPCServer

    result = JSONRPCServer().handle_environment_detect({})
    assert "tools" in result and "android_ready" in result and "appium_drivers" in result


# ---- ANDROID_HOME / appium_android_ready split ----


def _appium_android_runner():
    """adb + appium present with the uiautomator2 driver installed."""

    def run(cmd):
        if cmd[:2] == ["appium", "driver"]:
            return (0, "- uiautomator2@3.0.0 [installed]")
        return {
            "adb": (0, "Android Debug Bridge version 1.0.41"),
            "appium": (0, "2.11.3"),
        }.get(cmd[0], (127, ""))

    return run


def test_android_home_detected_but_unset(monkeypatch):
    """SDK on disk but ANDROID_HOME/SDK_ROOT not exported: android_home is set,
    android_home_set is False, and to_dict carries an actionable fix hint."""
    monkeypatch.setattr(envmod, "resolve_android_home", lambda: "/opt/android/sdk")
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)

    env = detect_environment(run=_appium_android_runner())
    assert env.android_home == "/opt/android/sdk"
    assert env.android_home_set is False
    # adb usable + SDK path known + driver installed => appium path is ready.
    assert env.android_ready is True and env.appium_android_ready is True

    d = env.to_dict()
    assert d["android_home"] == "/opt/android/sdk" and d["android_home_set"] is False
    assert d["android_home_fix"] == "export ANDROID_HOME=/opt/android/sdk"


def test_android_home_set_no_fix_hint(monkeypatch):
    monkeypatch.setattr(envmod, "resolve_android_home", lambda: "/opt/android/sdk")
    monkeypatch.setenv("ANDROID_HOME", "/opt/android/sdk")
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)

    env = detect_environment(run=_appium_android_runner())
    assert env.android_home_set is True and env.appium_android_ready is True
    d = env.to_dict()
    assert "android_home_fix" not in d  # nothing to fix when it's exported


def test_android_home_absent_splits_adb_from_appium_readiness(monkeypatch):
    """No SDK path at all: adb-on-PATH keeps android_ready True (backward-compat),
    but appium_android_ready is False — the false 'ready' this fix targets."""
    monkeypatch.setattr(envmod, "resolve_android_home", lambda: None)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)

    env = detect_environment(run=_appium_android_runner())
    assert env.android_home is None and env.android_home_set is False
    assert env.android_ready is True  # adb still on PATH
    assert env.appium_android_ready is False  # but no SDK => Appium session would fail
    assert "android_home_fix" not in env.to_dict()


def test_appium_android_not_ready_without_driver(monkeypatch):
    """SDK present but the uiautomator2 driver isn't installed => not appium-ready."""
    monkeypatch.setattr(envmod, "resolve_android_home", lambda: "/opt/android/sdk")
    monkeypatch.setenv("ANDROID_HOME", "/opt/android/sdk")

    def run(cmd):
        if cmd[:2] == ["appium", "driver"]:
            return (0, "")  # no drivers installed
        return {"adb": (0, "adb 1.0.41"), "appium": (0, "2.11.3")}.get(cmd[0], (127, ""))

    env = detect_environment(run=run)
    assert env.android_ready is True and env.appium_android_ready is False


def test_to_dict_keeps_existing_keys(monkeypatch):
    """Backward-compat: the Kotlin plugin parses to_dict(); existing keys stay."""
    monkeypatch.setattr(envmod, "resolve_android_home", lambda: None)
    d = detect_environment(run=_runner({})).to_dict()
    for key in ("tools", "appium_drivers", "android_ready", "ios_ready"):
        assert key in d
    for key in ("android_home", "android_home_set", "appium_android_ready"):
        assert key in d


# ---- driver manager (npm >= 11 breaks `appium driver install/update`) ----


def _node_npm_runner(node, npm):
    """Runner that answers only node/npm version probes with the given outputs."""

    def run(cmd):
        if cmd[0] == "node":
            return (0, node) if node is not None else (127, "")
        if cmd[0] == "npm":
            return (0, npm) if npm is not None else (127, "")
        return (127, "")

    return run


def test_to_dict_flags_broken_driver_manager(monkeypatch):
    """npm >= 11 (Node >= 23): driver_manager_ok is False and to_dict carries the
    remediation, so the plugin can surface it."""
    monkeypatch.setattr(envmod, "resolve_android_home", lambda: None)
    env = detect_environment(run=_node_npm_runner("v25.0.0", "11.0.0"))
    assert env.driver_manager_ok is False
    assert env.driver_manager_fix is not None and "npm <= 10" in env.driver_manager_fix
    d = env.to_dict()
    assert d["driver_manager_ok"] is False
    assert "nvm install --lts" in d["driver_manager_fix"]


def test_to_dict_driver_manager_ok_on_npm_10(monkeypatch):
    monkeypatch.setattr(envmod, "resolve_android_home", lambda: None)
    d = detect_environment(run=_node_npm_runner("v20.11.0", "10.2.4")).to_dict()
    assert d["driver_manager_ok"] is True
    assert d["driver_manager_fix"] is None


def test_to_dict_driver_manager_ok_when_node_absent(monkeypatch):
    """No node/npm: can't diagnose, so ok=True (drivers may already be installed)."""
    monkeypatch.setattr(envmod, "resolve_android_home", lambda: None)
    d = detect_environment(run=_node_npm_runner(None, None)).to_dict()
    assert d["driver_manager_ok"] is True and d["driver_manager_fix"] is None


def test_to_dict_keeps_driver_manager_keys(monkeypatch):
    """Backward-compat: new keys are always present for the plugin to parse."""
    monkeypatch.setattr(envmod, "resolve_android_home", lambda: None)
    d = detect_environment(run=_node_npm_runner(None, None)).to_dict()
    assert "driver_manager_ok" in d and "driver_manager_fix" in d
