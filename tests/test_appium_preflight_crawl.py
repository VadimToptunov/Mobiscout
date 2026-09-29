"""An Appium-driven crawl fails fast with an actionable message when no Appium server is
reachable, instead of the silent 0-screen result a failed connection produces (review
P1.7). The adb-driven Android path must not require Appium at all.

These run the real ensure_appium decision through _make_driver with its seams injected,
so they behave the same whether or not the machine has Appium installed."""

import functools

import pytest

import framework.crawler.pipeline as pipeline
from framework.crawler import appium_server
from framework.crawler.errors import CrawlerDriverError

_ANDROID_APPIUM = {"package": "com.x", "platform": "android", "driver": "appium"}
_IOS = {"package": "com.x", "platform": "ios"}


def _unreachable(_server):
    return False, None


def _seam(monkeypatch, **seams):
    """Point _make_driver at the real ensure_appium with the given seams injected."""
    real = appium_server.ensure_appium
    monkeypatch.setattr(appium_server, "ensure_appium", functools.partial(real, status=_unreachable, **seams))


_AUTOSTART_FAILED = "Appium exited before it became ready (started from /opt/homebrew/bin/appium)."


class _FailingAutostart:
    """An installed Appium whose auto-start fails (its real message is pinned in
    test_appium_autostart; here we only care that it reaches the caller intact)."""

    def __init__(self, executable):
        self.executable = executable

    def start(self):
        raise CrawlerDriverError(_AUTOSTART_FAILED)


@pytest.mark.parametrize("config", [_ANDROID_APPIUM, _IOS], ids=["android-appium", "ios"])
def test_crawl_fails_actionably_when_appium_is_not_installed(monkeypatch, config):
    _seam(monkeypatch, finder=lambda: None, server_factory=lambda exe: pytest.fail("nothing to start"))
    with pytest.raises(CrawlerDriverError) as exc:
        pipeline._make_driver(config)
    msg = str(exc.value)
    assert "Appium server not reachable" in msg and "npm install -g appium" in msg


@pytest.mark.parametrize("config", [_ANDROID_APPIUM, _IOS], ids=["android-appium", "ios"])
def test_crawl_fails_actionably_when_appium_autostart_fails(monkeypatch, config):
    _seam(monkeypatch, finder=lambda: "/opt/homebrew/bin/appium", server_factory=_FailingAutostart)
    with pytest.raises(CrawlerDriverError) as exc:
        pipeline._make_driver(config)
    assert str(exc.value) == _AUTOSTART_FAILED


def test_adb_crawl_does_not_probe_appium(monkeypatch):
    # The default Android path is adb — it must never require or probe Appium.
    monkeypatch.setattr(appium_server, "ensure_appium", lambda *a, **k: pytest.fail("adb path must not use Appium"))
    driver, owns_session = pipeline._make_driver({"package": "com.x", "platform": "android"})
    assert owns_session is False  # adb path doesn't own an Appium session
