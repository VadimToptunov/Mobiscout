"""IOSCrawlerDriver conforms to the CrawlerDriver protocol and drives an Appium
XCUITest session. The session itself needs a simulator, so here we only pin the
public surface (import, name, protocol methods) — the live crawl is exercised
separately against a booted simulator."""

from framework.crawler import IOSCrawlerDriver
from framework.crawler.app_crawler import CrawlerDriver


def test_ios_driver_is_exported_and_named():
    assert IOSCrawlerDriver.__name__ == "IOSCrawlerDriver"


def test_ios_driver_implements_crawler_protocol():
    for method in ("page_source", "tap", "back", "current_package"):
        assert callable(getattr(IOSCrawlerDriver, method, None)), f"missing {method}"


def test_ios_driver_is_structurally_a_crawler_driver():
    # Duck-typed protocol: the class exposes everything the crawler calls.
    assert issubclass(IOSCrawlerDriver, object)
    assert set(
        CrawlerDriver.__protocol_attrs__
        if hasattr(CrawlerDriver, "__protocol_attrs__")
        else {"page_source", "tap", "back", "current_package"}
    ) <= set(dir(IOSCrawlerDriver))
