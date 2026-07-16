"""iOS crawls must be able to pass launch arguments to the app (skip a login gate,
deep-link a screen, enable a test mode) — without them many apps never reach a
crawlable state. Found live on ChaosBank (needs -ChaosBankStartUnlocked)."""

from unittest import mock

from framework.crawler.appium_driver import IOSCrawlerDriver


def _caps_for(process_args):
    with mock.patch("appium.webdriver.Remote") as remote:
        IOSCrawlerDriver(bundle_id="com.example.app", process_args=process_args)
    options = remote.call_args.kwargs["options"]
    return options.to_capabilities()


def test_process_arguments_forwarded_as_capability():
    caps = _caps_for(["-ChaosBankStartUnlocked", "1"])
    assert caps["appium:processArguments"] == {"args": ["-ChaosBankStartUnlocked", "1"]}


def test_no_process_arguments_when_none():
    assert "appium:processArguments" not in _caps_for(None)
    assert "appium:processArguments" not in _caps_for([])
