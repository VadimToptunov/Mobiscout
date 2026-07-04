"""Tests for the crawl artifact exporter (element inventory + flow map)."""

import json

from framework.crawler.app_crawler import AppCrawler
from framework.crawler.report import inventory_json, inventory_markdown, inventory_json_str
from tests.test_crawler import APP, FakeDriver


def test_inventory_json_lists_screens_elements_flows():
    result = AppCrawler(FakeDriver(), APP, max_steps=100).crawl()
    data = inventory_json(result, APP)
    assert data["app_package"] == APP
    assert data["screen_count"] == len(result.screens) >= 1
    s1 = data["screens"][0]
    assert "elements" in s1 and s1["element_count"] == len(s1["elements"])
    # each element carries a recommended locator
    assert all("locator" in e for e in s1["elements"])
    # login button element exposes a usable locator
    assert any(e["locator"]["value"] == "id/login" for e in s1["elements"])
    # flows reference screen indices
    assert data["flows"] and all("from" in f and "to" in f and "tap" in f for f in data["flows"])
    # json serialisable
    json.loads(inventory_json_str(result, APP))


def test_inventory_markdown_has_tables_and_a11y_section():
    result = AppCrawler(FakeDriver(), APP, max_steps=100).crawl()
    md = inventory_markdown(result, APP)
    assert "# Screen inventory" in md
    assert "| Element | Locator | Interactive |" in md
    assert "## Discovered flows" in md
    assert "## Accessibility" in md
