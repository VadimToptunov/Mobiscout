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


class _ActiveElement:
    def __init__(self, calls):
        self._calls = calls

    def send_keys(self, text):
        self._calls.append(("send_keys", text))


class _SwitchTo:
    def __init__(self, calls):
        self.active_element = _ActiveElement(calls)


class _FakeSession:
    def __init__(self):
        self.calls = []
        self.page_source = "<hierarchy/>"
        self.current_package = "com.example.app"
        self.switch_to = _SwitchTo(self.calls)

    def update_settings(self, s):
        self.calls.append(("settings", s))

    def execute_script(self, name, args):
        self.calls.append(("script", name, args))

    def get_window_size(self):
        return {"width": 1080, "height": 1920}

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


# --- The three methods the crawler relies on (previously missing, so the crawler's
# hasattr-guarded type_text/scroll/refresh silently no-op'd on Appium-Android). ---


def test_type_text_sends_keys_to_active_element():
    d = _driver()
    d.type_text("hello world")
    assert ("send_keys", "hello world") in d._driver.calls


def test_scroll_uses_scroll_gesture():
    d = _driver()
    d.scroll("down")
    scripts = [c for c in d._driver.calls if c[0] == "script" and c[1] == "mobile: scrollGesture"]
    assert scripts, "scroll must issue a mobile: scrollGesture"
    assert scripts[0][2]["direction"] == "down"


def test_refresh_rereads_page_source():
    d = _driver()
    assert d.refresh(wait=0) == "<hierarchy/>"


def test_crawler_required_methods_are_present():
    # The crawler calls these guarded by hasattr; before the fix they were absent,
    # so form-fill / scroll / async-await silently did nothing on Appium-Android.
    d = _driver()
    for name in ("type_text", "scroll", "refresh"):
        assert callable(getattr(d, name, None)), f"AndroidAppiumDriver.{name} is missing"
