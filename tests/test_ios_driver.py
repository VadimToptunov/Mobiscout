"""IOSCrawlerDriver drives an Appium XCUITest session. The session needs a
simulator, so these mock it and pin the *wire calls* each gesture makes — a tap
that lands on the wrong pixel, a Back swiped from the wrong edge or a scroll that
goes the wrong way all fail silently on a device, and only show up as a crawl
that maps nothing."""

from unittest import mock

import pytest

from framework.crawler import IOSCrawlerDriver, webview

_BID = "com.example.app"
_SIZE = {"width": 390, "height": 844}


@pytest.fixture()
def driver(monkeypatch):
    """A driver over a mocked Appium session, with settling stubbed out (it polls
    page_source and only adds latency here)."""
    with mock.patch("appium.webdriver.Remote") as remote:
        d = IOSCrawlerDriver(bundle_id=_BID)
    d._driver = remote.return_value
    d._driver.get_window_size.return_value = _SIZE
    monkeypatch.setattr(d, "_settle_wait", lambda: None)
    return d


def _scripts(driver):
    """(script, args) for every execute_script the driver issued."""
    return [(c.args[0], c.args[1] if len(c.args) > 1 else None) for c in driver._driver.execute_script.call_args_list]


def test_tap_issues_a_mobile_tap_at_the_point(driver):
    driver.tap(10, 20)
    assert _scripts(driver) == [("mobile: tap", {"x": 10, "y": 20})]


def test_tap_in_a_webview_clicks_the_dom_element(driver, monkeypatch):
    clicked = []
    monkeypatch.setattr(webview, "click_web", lambda drv, web, x, y: clicked.append((x, y)) or True)
    driver._web = {"xml": "<hierarchy/>"}

    driver.tap(10, 20)
    assert clicked == [(10, 20)]
    assert _scripts(driver) == []  # the DOM click replaces the native tap


def test_tap_in_a_webview_never_falls_through_to_a_native_tap(driver, monkeypatch):
    # Web coordinates are CSS/viewport pixels, not device points: a fallthrough taps
    # an arbitrary device pixel — possibly a control the blocklist deliberately skipped.
    monkeypatch.setattr(webview, "click_web", lambda drv, web, x, y: False)
    driver._web = {"xml": "<hierarchy/>"}

    driver.tap(10, 20)
    assert _scripts(driver) == []


def test_back_drags_from_the_left_edge(driver):
    # iOS Back is the left-edge swipe. Starting from the right edge is the
    # forward/Control-Centre side and never pops the screen.
    driver.back()
    ((script, args),) = _scripts(driver)
    assert script == "mobile: dragFromToForDuration"
    assert args["fromX"] == 2 and args["toX"] > args["fromX"]
    assert args["fromY"] == args["toY"] == _SIZE["height"] // 2


@pytest.mark.parametrize("direction", ["down", "up"])
def test_scroll_asks_xcuitest_for_the_requested_direction(driver, direction):
    driver.scroll(direction)
    assert _scripts(driver) == [("mobile: scroll", {"direction": direction})]


@pytest.mark.parametrize("direction,downwards", [("down", True), ("up", False)])
def test_scroll_drag_fallback_swipes_the_right_way(driver, direction, downwards):
    # When XCUITest can't resolve a scrollable it falls back to a drag; inverting it
    # means below-the-fold content is never revealed while the crawl looks healthy.
    def exec_script(script, *args):
        if script == "mobile: scroll":
            raise RuntimeError("no scrollable view")
        return None

    driver._driver.execute_script.side_effect = exec_script
    driver.scroll(direction)

    script, args = _scripts(driver)[-1]
    assert script == "mobile: dragFromToForDuration"
    assert (args["fromY"] > args["toY"]) is downwards


def test_type_text_types_into_the_focused_element(driver):
    driver.type_text("hunter2")
    driver._driver.switch_to.active_element.send_keys.assert_called_once_with("hunter2")


def test_clear_field_clears_the_focused_element(driver):
    # A re-fill must replace, not append — otherwise the negative probe's value and
    # the positive one end up concatenated and neither branch is really exercised.
    driver.clear_field()
    driver._driver.switch_to.active_element.clear.assert_called_once_with()
    driver._driver.switch_to.active_element.send_keys.assert_not_called()
