"""AndroidAppiumDriver: capability building and the CrawlerDriver protocol,
exercised with an injected fake session (no Appium server / device needed)."""

from framework.crawler.appium_android import AndroidAppiumDriver, build_uiautomator2_options


def test_options_are_uiautomator2_android():
    caps = build_uiautomator2_options(
        "com.example.app",
        app_activity=".Main",
        udid="emulator-5554",
        extra_caps={"bstack:options": {"deviceName": "Pixel 8"}},
    ).to_capabilities()
    assert caps["platformName"].lower() == "android"
    assert caps["appium:automationName"].lower() == "uiautomator2"
    assert caps["appium:appPackage"] == "com.example.app"
    assert caps["appium:appActivity"] == ".Main"
    assert caps["appium:udid"] == "emulator-5554"
    assert caps["appium:noReset"] is True
    # extra caps are passed through verbatim (cloud grids etc.)
    assert caps["bstack:options"] == {"deviceName": "Pixel 8"}


class _FakeSession:
    def __init__(self):
        self.calls = []
        self.page_source = "<hierarchy/>"
        self.current_package = "com.example.app"

    def update_settings(self, s):
        self.calls.append(("settings", s))

    def execute_script(self, name, args):
        self.calls.append(("script", name, args))

    def back(self):
        self.calls.append(("back",))

    def quit(self):
        self.calls.append(("quit",))


def _driver():
    return AndroidAppiumDriver("com.example.app", settle=0, _session=_FakeSession())


def test_sets_idle_timeout_on_start():
    d = _driver()
    assert ("settings", {"waitForIdleTimeout": 100}) in d._driver.calls


def test_tap_uses_click_gesture():
    d = _driver()
    d.tap(10, 20)
    assert ("script", "mobile: clickGesture", {"x": 10, "y": 20}) in d._driver.calls


def test_back_and_page_source_and_package():
    d = _driver()
    d.back()
    assert ("back",) in d._driver.calls
    assert d.page_source() == "<hierarchy/>"
    assert d.current_package() == "com.example.app"


def test_quit_delegates():
    d = _driver()
    d.quit()
    assert ("quit",) in d._driver.calls
