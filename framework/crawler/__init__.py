"""
Autonomous app crawler.

    driver (Appium) --> AppCrawler.crawl() --> CrawlResult (screens + transitions)

The CrawlResult can be turned into codegen IR to generate tests for the paths
the crawler discovered — the "explore -> automate" seam.
"""

from framework.crawler.app_crawler import (
    AppCrawler,
    CrawlElement,
    CrawlerDriver,
    CrawlResult,
    CrawlScreen,
    DEFAULT_BLOCKLIST,
    parse_screen,
)
from framework.crawler.to_codegen import build_test_model


class AppiumCrawlerDriver:
    """Adapt a real Appium (UiAutomator2) driver to the CrawlerDriver protocol.

    Not unit-tested (it needs a device); the crawl logic is exercised against a
    fake driver instead.
    """

    def __init__(self, driver):
        self._driver = driver

    def page_source(self) -> str:
        return self._driver.page_source

    def tap(self, x: int, y: int) -> None:
        # uiautomator2's tap-by-coordinates gesture (TouchAction is deprecated).
        self._driver.execute_script("mobile: clickGesture", {"x": x, "y": y})

    def back(self) -> None:
        self._driver.back()

    def current_package(self) -> str:
        return self._driver.current_package


__all__ = [
    "AppCrawler",
    "AppiumCrawlerDriver",
    "CrawlElement",
    "CrawlerDriver",
    "CrawlResult",
    "CrawlScreen",
    "DEFAULT_BLOCKLIST",
    "parse_screen",
    "build_test_model",
]
