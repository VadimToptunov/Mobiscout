"""iOS re-launch: the crawler's recovery must be able to bring a drifted /
backgrounded iOS app back to the foreground (Back can't), mirroring adb. Tests
mock the Appium session — no device."""

from unittest import mock

import pytest

from framework.crawler.appium_driver import IOSCrawlerDriver

_BID = "com.example.app"


def _driver():
    with mock.patch("appium.webdriver.Remote") as remote:
        d = IOSCrawlerDriver(bundle_id=_BID)
    d._driver = remote.return_value
    d._driver.page_source = "<XCUIElementTypeApplication/>"  # keep settle happy
    return d


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import framework.crawler.appium_driver as ap

    monkeypatch.setattr(ap.time, "sleep", lambda s: None)


def test_launch_activates_the_app_and_confirms_foreground():
    d = _driver()
    d._driver.execute_script.side_effect = lambda script, *a: {"bundleId": _BID}
    assert d.launch() is True
    d._driver.activate_app.assert_called_once_with(_BID)


def test_launch_falls_back_to_mobile_launchapp():
    d = _driver()
    d._driver.activate_app.side_effect = RuntimeError("no activate")

    calls = []

    def exec_script(script, *args):
        calls.append((script, args))
        return {"bundleId": _BID}

    d._driver.execute_script.side_effect = exec_script
    assert d.launch() is True
    assert any(script == "mobile: launchApp" for script, _ in calls)


def test_launch_returns_false_if_app_never_foregrounds():
    d = _driver()
    d._driver.execute_script.side_effect = lambda script, *a: {"bundleId": "com.other"}
    assert d.launch(tries=3) is False
