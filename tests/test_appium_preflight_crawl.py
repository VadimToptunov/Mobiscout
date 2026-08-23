"""An Appium-driven crawl fails fast with an actionable message when no Appium server is
reachable, instead of the silent 0-screen result a failed connection produces (review
P1.7). The adb-driven Android path must not require Appium at all."""

import pytest

import framework.crawler.pipeline as pipeline
from framework.crawler.errors import CrawlerDriverError


def test_android_appium_crawl_fails_actionably_when_server_unreachable(monkeypatch):
    monkeypatch.setattr("framework.health.preflight.appium_status", lambda server: (False, None))
    with pytest.raises(CrawlerDriverError) as exc:
        pipeline._make_driver({"package": "com.x", "platform": "android", "driver": "appium"})
    msg = str(exc.value)
    assert "Appium server not reachable" in msg and "npm install -g appium" in msg


def test_ios_crawl_requires_appium(monkeypatch):
    monkeypatch.setattr("framework.health.preflight.appium_status", lambda server: (False, None))
    with pytest.raises(CrawlerDriverError):
        pipeline._make_driver({"package": "com.x", "platform": "ios"})


def test_adb_crawl_does_not_probe_appium(monkeypatch):
    # The default Android path is adb — it must never require or probe Appium.
    calls = {"n": 0}

    def _probe(server):
        calls["n"] += 1
        return (False, None)

    monkeypatch.setattr("framework.health.preflight.appium_status", _probe)
    driver, owns_session = pipeline._make_driver({"package": "com.x", "platform": "android"})
    assert calls["n"] == 0
    assert owns_session is False  # adb path doesn't own an Appium session
