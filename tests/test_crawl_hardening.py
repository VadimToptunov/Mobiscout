"""Crawl-robustness hardening (no device):

* the wall-clock budget stops a crawl even when the step budget is huge; and
* the Android driver bounds the uiautomator source dump, so a WebView-poisoned
  dump surfaces as a driver error (and a wedged session doesn't block quit)
  instead of hanging the run.
"""

import time

import pytest

import framework.crawler.app_crawler as ac
import framework.crawler.appium_android as aa
from framework.crawler.app_crawler import AppCrawler
from framework.crawler.errors import CrawlerDriverError
from tests.test_crawler import APP, FakeDriver


def test_wall_clock_budget_stops_before_step_budget(monkeypatch):
    # Swap only app_crawler's module-local ``time`` (it uses just monotonic), so a
    # frozen clock drives the budget without touching the global time module that
    # thread.join / pytest rely on.
    clock = {"t": 1000.0}

    class _FakeTime:
        @staticmethod
        def monotonic():
            return clock["t"]

    monkeypatch.setattr(ac, "time", _FakeTime)
    crawler = AppCrawler(FakeDriver(), APP, max_steps=100000, max_seconds=5.0)

    # Jump the clock past the deadline (set at crawl start = 1000 + 5) right before
    # the DFS loop, so the budget — not the step count — is what stops the crawl.
    original = crawler._explore

    def explore(result):
        clock["t"] = 1006.0
        return original(result)

    monkeypatch.setattr(crawler, "_explore", explore)
    result = crawler.crawl()

    assert result.steps < 100000  # stopped by the clock, not the (huge) step budget
    assert not crawler._within_budget(result)  # deadline is in the past


def test_no_budget_by_default_uses_step_limit():
    # max_seconds defaults to 0 (disabled): the deadline is infinite, so a normal
    # crawl still runs to completion under the step budget.
    result = AppCrawler(FakeDriver(), APP, max_steps=100).crawl()
    assert len(result.screens) == 4  # full graph, unaffected by the budget code


class _OkSession:
    contexts = ["NATIVE_APP"]
    page_source = "<hierarchy rotation='0'></hierarchy>"

    def update_settings(self, *a, **k):
        pass


class _HangSession:
    contexts = ["NATIVE_APP"]

    def update_settings(self, *a, **k):
        pass

    @property
    def page_source(self):
        time.sleep(30)  # simulate a WebView-poisoned dump that never returns
        return "<hierarchy/>"

    def quit(self):
        time.sleep(30)  # a wedged session blocks quit() too


def test_native_source_returns_normally():
    drv = aa.AndroidAppiumDriver(app_package="x", _session=_OkSession())
    assert "hierarchy" in drv.page_source()
    assert drv._wedged is False


def test_native_source_dump_timeout_raises_and_does_not_wedge_quit(monkeypatch):
    monkeypatch.setattr(aa, "_SOURCE_TIMEOUT_S", 0.3)
    drv = aa.AndroidAppiumDriver(app_package="x", _session=_HangSession())

    with pytest.raises(CrawlerDriverError):
        drv.page_source()
    assert drv._wedged is True

    # quit() must return immediately even though the dump/quit calls still hang.
    started = time.time()
    drv.quit()
    assert time.time() - started < 1.0
