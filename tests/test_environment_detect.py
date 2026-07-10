"""Environment detection: probe the automation toolchain with an injected runner,
so it's fully testable without the tools installed."""

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
