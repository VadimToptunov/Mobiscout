"""Transient-failure resilience for the crawler.

Live e2e on an emulator surfaced two fragilities: a single hung adb round-trip
(``subprocess.TimeoutExpired``) aborted the whole crawl, and that raw exception
escaped :meth:`AppCrawler.crawl`, throwing away every screen gathered so far.
These tests pin the two guarantees added in response:

1. :meth:`AdbCrawlerDriver._run` retries a transient timeout and only raises
   :class:`CrawlerDriverError` once every attempt is exhausted.
2. :meth:`AppCrawler.crawl` catches that error and returns the partial map — a
   device hiccup degrades to a partial kit instead of crashing the run.
"""

import subprocess

import pytest

from framework.crawler.adb_driver import AdbCrawlerDriver
from framework.crawler.app_crawler import AppCrawler
from framework.crawler.errors import CrawlerDriverError

APP = "com.example.app"
_SCREEN = (
    '<hierarchy rotation="0">'
    '<node class="android.widget.Button" resource-id="id/a" text="A" '
    'content-desc="" clickable="true" bounds="[0,0][100,50]"/>'
    "</hierarchy>"
)


class _FakeProc:
    def __init__(self, stdout: str):
        self.stdout = stdout


def _no_sleep(monkeypatch):
    monkeypatch.setattr("framework.crawler.adb_driver.time.sleep", lambda *_: None)


def test_run_retries_transient_timeout_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:  # first two attempts hang, third succeeds
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
        return _FakeProc("ok")

    monkeypatch.setattr("framework.crawler.adb_driver.subprocess.run", fake_run)
    _no_sleep(monkeypatch)

    driver = AdbCrawlerDriver(retries=2)
    assert driver._run("shell", "echo", "hi") == "ok"
    assert calls["n"] == 3  # retried twice before succeeding


def test_run_raises_crawler_driver_error_after_exhausting_retries(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr("framework.crawler.adb_driver.subprocess.run", fake_run)
    _no_sleep(monkeypatch)

    driver = AdbCrawlerDriver(retries=2)
    with pytest.raises(CrawlerDriverError):
        driver._run("shell", "echo", "hi")
    assert calls["n"] == 3  # 1 initial + 2 retries, then give up


def test_run_does_not_retry_when_retries_zero(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr("framework.crawler.adb_driver.subprocess.run", fake_run)
    _no_sleep(monkeypatch)

    with pytest.raises(CrawlerDriverError):
        AdbCrawlerDriver(retries=0)._run("shell", "echo")
    assert calls["n"] == 1  # no extra attempts


def test_crawl_returns_partial_result_on_driver_error():
    """A driver failure mid-crawl keeps the screens gathered before it."""

    class FlakyDriver:
        def __init__(self):
            self.taps = 0

        def page_source(self):
            return _SCREEN

        def current_package(self):
            return APP

        def back(self):
            pass

        def tap(self, x, y):
            self.taps += 1
            raise CrawlerDriverError("adb wedged mid-crawl")

    driver = FlakyDriver()
    result = AppCrawler(driver, APP, max_steps=10).crawl()

    # The entry screen was recorded before the first tap failed -> partial map,
    # no exception escapes crawl().
    assert len(result.screens) == 1
    assert driver.taps == 1
