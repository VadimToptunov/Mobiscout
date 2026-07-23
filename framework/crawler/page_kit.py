"""
Framework-structured output from a crawl — Page Objects, a conftest, and tests
that *use* the page objects, instead of one flat smoke file.

Real teams keep locators in Page Objects, the driver in a shared fixture, and
tests that read like intent. This turns a CrawlResult into exactly that layout:

    pages/<screen>_page.py    one Page Object per screen (ranked locators + accessors)
    conftest.py               the Appium driver fixture (platform-aware)
    tests/test_navigation.py  tests that drive the pages (POM style)

Python + pytest + Appium for now; the same idea maps to the other targets.
"""

from __future__ import annotations

import re
from typing import Dict, List

from framework.codegen.emitters._naming import pascal, snake
from framework.codegen.ir import Platform, TestModel
from framework.codegen.page_object import PageObject, PageObjectField, _env
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import _owned, selector_for


def _screen_name(index: int, screen: CrawlScreen, app_package: str) -> str:
    """A readable, valid page-class prefix: from a title-like text, else Screen{N}."""
    for e in _owned(screen, app_package):
        if not e.clickable and (e.text or "").strip():
            name = re.sub(r"[^0-9a-zA-Z]", "", pascal(e.text.strip()))
            if name and not name[0].isdigit():
                return name
    return f"Screen{index}"


def _accessor(element: CrawlElement) -> str:
    """A valid Python identifier for an element accessor (used identically in the
    page object and the tests, so they always agree)."""
    raw = element.text or element.content_desc or element.resource_id.split("/")[-1] or element.class_name
    name = re.sub(r"[^0-9a-zA-Z_]", "_", snake(raw)).strip("_")
    if not name or name[0].isdigit():
        name = "e_" + name
    return name or "element"


def _page_objects(result: CrawlResult, app_package: str) -> Dict[str, str]:
    """One Page Object module per screen (reusing the page-object template)."""
    template = _env().get_template("page_object.py.j2")
    out: Dict[str, str] = {}
    names: List[str] = []
    for i, screen in enumerate(result.screens.values(), 1):
        owned = _owned(screen, app_package)
        fields: List[PageObjectField] = []
        seen = set()
        for e in owned:
            sel = selector_for(e, owned, screen.platform)
            if sel is None:
                continue
            name = _accessor(e)
            if name in seen:
                continue
            seen.add(name)
            fields.append(PageObjectField(name=name, selector=sel))
        if not fields:
            continue
        page_name = _screen_name(i, screen, app_package)
        base = page_name if page_name not in names else f"{page_name}{i}"
        names.append(base)
        po = PageObject(class_name=f"{base}Page", screen_name=base, fields=fields)
        out[f"pages/{snake(po.class_name)}.py"] = template.render(po=po)
    return out


def _conftest(model: TestModel) -> str:
    is_ios = model.platform is Platform.IOS
    if is_ios:
        imp = "from appium.options.ios import XCUITestOptions"
        setup = (
            "    options = XCUITestOptions()\n"
            '    options.platform_name = "iOS"\n'
            '    options.automation_name = "XCUITest"\n'
            f"    options.bundle_id = {model.app_package!r}\n"
        )
    else:
        imp = "from appium.options.android import UiAutomator2Options"
        activity = f"    options.app_activity = {model.app_activity!r}\n" if model.app_activity else ""
        setup = (
            "    options = UiAutomator2Options()\n"
            '    options.platform_name = "Android"\n'
            '    options.automation_name = "UiAutomator2"\n'
            f"    options.app_package = {model.app_package!r}\n"
            f"{activity}"
        )
    return (
        '"""Shared pytest fixtures — one Appium session per test."""\n\n'
        "import pytest\n"
        "from appium import webdriver\n"
        f"{imp}\n\n\n"
        "@pytest.fixture()\n"
        "def driver():\n"
        f"{setup}"
        '    drv = webdriver.Remote("http://localhost:4723", options=options)\n'
        "    yield drv\n"
        "    drv.quit()\n"
    )


def _navigation_tests(result: CrawlResult, app_package: str, pages: Dict[str, str]) -> str:
    """POM-style tests: from the entry page, tap through and assert the landmark
    on the destination page — using the page objects, not raw locators."""
    fps = list(result.screens)
    if not fps:
        return ""
    name_of = {}
    for i, (fp, screen) in enumerate(result.screens.items(), 1):
        name_of[fp] = _screen_name(i, screen, app_package)

    start = fps[0]
    seen = set()
    used_classes = set()
    bodies: List[str] = []
    n = 0
    for from_fp, element, to_fp in result.transitions:
        if from_fp != start or to_fp == start:
            continue
        acc = _accessor(element)
        if acc in seen:
            continue
        target = result.screens.get(to_fp)
        if target is None:
            continue
        landmark = next(
            (
                _accessor(e)
                for e in _owned(target, app_package)
                if selector_for(e, _owned(target, app_package), target.platform)
            ),
            None,
        )
        if landmark is None:
            continue
        seen.add(acc)
        n += 1
        src_cls, dst_cls = f"{name_of[start]}Page", f"{name_of[to_fp]}Page"
        used_classes.update({src_cls, dst_cls})
        bodies += [
            f"def test_navigate_{n}(driver):",
            f'    """{name_of[start]} -> {name_of[to_fp]} via {acc}."""',
            f"    {src_cls}(driver).{acc}().click()",
            f"    assert {dst_cls}(driver).{landmark}().is_displayed()",
            "",
        ]
    if not n:
        return ""
    lines = ['"""Navigation tests — drive the Page Objects (POM style)."""', ""]
    for cls in sorted(used_classes):
        lines.append(f"from pages.{snake(cls)} import {cls}")
    lines.append("")
    lines += bodies
    return "\n".join(lines)


def build_framework_kit(result: CrawlResult, model: TestModel, app_package: str) -> Dict[str, str]:
    """A proper pytest framework layout from a crawl (relative_path -> content)."""
    files: Dict[str, str] = {}
    pages = _page_objects(result, app_package)
    if not pages:
        return files
    files["pages/__init__.py"] = ""
    files.update(pages)
    files["conftest.py"] = _conftest(model)
    nav = _navigation_tests(result, app_package, pages)
    if nav:
        files["tests/test_navigation.py"] = nav
        files["tests/__init__.py"] = ""
    return files
