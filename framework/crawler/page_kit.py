"""
Framework-structured output from a crawl — a Page-Object test framework, not one flat
smoke file.

Real teams keep locators inside page objects, the driver in a shared fixture, and tests
that read like intent. The crawl is first turned into the language-agnostic framework
model (:mod:`framework.codegen.framework_model`) — pages with intention methods and a
distinctive identity, scenarios as page calls — and then rendered per language. Python
(pytest + Appium) is rendered here::

    conftest.py              one Appium session per run + a cold app restart per test
    pages/base_page.py       locating / waiting / acting / settling, written once
    pages/<screen>_page.py   private locators + intention methods per screen
    tests/test_<screen>.py   scenarios about that screen
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.framework_model import build_framework_model
from framework.codegen.framework_python import render_python
from framework.codegen.ir import TestModel
from framework.crawler.app_crawler import CrawlResult


def build_framework_kit(result: CrawlResult, model: TestModel, app_package: str) -> Dict[str, str]:
    """A pytest Page-Object framework layout from a crawl (relative_path -> content)."""
    return render_python(build_framework_model(result, model, app_package))
