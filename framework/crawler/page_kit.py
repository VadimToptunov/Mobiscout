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
from framework.codegen.ir import ActionType, AssertionType, Platform, Selector, TestModel
from framework.codegen.page_object import PageObject, PageObjectField, _env
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import _owned, selector_for


def _sel_key(selector: Selector) -> tuple:
    """A stable key linking a model step's selector to a Page Object accessor. Both the
    page objects and the model's steps come from ``selector_for`` on the same crawl
    elements, so the (strategy, value) of the primary locator matches on both sides."""
    return (selector.strategy.value, selector.value)


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


def _page_objects(result: CrawlResult, app_package: str) -> tuple:
    """One Page Object module per screen (reusing the page-object template). Returns
    ``(files, page_of, pages)`` where ``page_of`` maps a selector key to
    ``(PageClass, accessor)`` so the flow tests can drive elements through the page
    objects, and ``pages`` maps a screen fingerprint to ``(PageClass, {selector key:
    accessor})`` — the names *actually emitted* for that screen. The navigation tests
    read from ``pages`` instead of re-deriving names, because both the class name and
    the accessor name are de-duplicated here; a recomputed name points at a class that
    has no such method."""
    template = _env().get_template("page_object.py.j2")
    out: Dict[str, str] = {}
    page_of: Dict[tuple, tuple] = {}
    pages: Dict[str, tuple] = {}
    names: List[str] = []
    for i, (fp, screen) in enumerate(result.screens.items(), 1):
        owned = _owned(screen, app_package)
        fields: List[PageObjectField] = []
        taken: set = set()
        for e in owned:
            sel = selector_for(e, owned, screen.platform)
            if sel is None:
                continue
            # Two elements often share a label — a header and the button under it, two
            # "Buy" rows — and so an accessor name. Dropping the loser removed it from
            # the page object entirely, which silently deleted every step targeting it:
            # the POM kit lost its taps and went red against a working app. Suffix the
            # duplicate instead, so both stay drivable.
            accessor = _accessor(e)
            name, n = accessor, 2
            while name in taken:
                name, n = f"{accessor}_{n}", n + 1
            taken.add(name)
            fields.append(PageObjectField(name=name, selector=sel))
        if not fields:
            continue
        page_name = _screen_name(i, screen, app_package)
        base = page_name if page_name not in names else f"{page_name}{i}"
        names.append(base)
        po = PageObject(class_name=f"{base}Page", screen_name=base, fields=fields)
        for f in fields:
            page_of.setdefault(_sel_key(f.selector), (po.class_name, f.name))
        pages[fp] = (po.class_name, {_sel_key(f.selector): f.name for f in fields})
        out[f"pages/{snake(po.class_name)}.py"] = template.render(po=po)
    return out, page_of, pages


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
        "import os\n\n"
        "import pytest\n"
        "from appium import webdriver\n"
        f"{imp}\n\n\n"
        "@pytest.fixture()\n"
        "def driver():\n"
        f"{setup}"
        # Every other target reads this env var, and the README written next to this kit
        # documents it — a hard-coded localhost made a POM kit unusable against the
        # remote hub or cloud grid the crawl itself ran on.
        "    # Run anywhere without regenerating: point at a different Appium/cloud-grid\n"
        "    # hub with MOBISCOUT_APPIUM_SERVER.\n"
        '    _server = os.environ.get("MOBISCOUT_APPIUM_SERVER", "http://localhost:4723")\n'
        "    drv = webdriver.Remote(_server, options=options)\n"
        "    yield drv\n"
        "    drv.quit()\n"
    )


def _navigation_tests(result: CrawlResult, app_package: str, pages: Dict[str, tuple]) -> str:
    """POM-style tests: from the entry page, tap through and assert a landmark that is
    distinctive to the destination page — using the page objects, not raw locators.

    Both classes and both accessors are looked up in ``pages`` (the names the page
    objects really carry) rather than recomputed, so a de-duplicated title or accessor
    can't send the test to a class that has no such method."""
    fps = list(result.screens)
    if not fps:
        return ""

    start = fps[0]
    if start not in pages:
        return ""
    src_cls, src_fields = pages[start]
    source = result.screens[start]
    source_owned = _owned(source, app_package)
    source_keys = {(e.content_desc or e.text or e.resource_id) for e in source_owned}
    seen = set()
    used_classes = set()
    bodies: List[str] = []
    n = 0
    for from_fp, element, to_fp in result.transitions:
        if from_fp != start or to_fp == start:
            continue
        tap_sel = selector_for(element, source_owned, source.platform)
        acc = src_fields.get(_sel_key(tap_sel)) if tap_sel is not None else None
        if acc is None or acc in seen:
            continue
        target = result.screens.get(to_fp)
        if target is None or to_fp not in pages:
            continue
        dst_cls, dst_fields = pages[to_fp]
        target_owned = _owned(target, app_package)
        # The landmark must be *distinctive* to the destination. The first element in
        # dump order is usually shared chrome (an app bar, a logo, a title) that is on
        # screen before the tap too, so asserting it passes even when the tap navigated
        # nowhere. Same ranking the flat emitters apply; no distinctive element means no
        # provable arrival, so no test rather than one that cannot fail.
        landmark = None
        for e in target_owned:
            key = e.content_desc or e.text or e.resource_id
            if not key or key in source_keys:
                continue
            sel = selector_for(e, target_owned, target.platform)
            landmark = dst_fields.get(_sel_key(sel)) if sel is not None else None
            if landmark is not None:
                break
        if landmark is None:
            continue
        seen.add(acc)
        n += 1
        used_classes.update({src_cls, dst_cls})
        bodies += [
            f"def test_navigate_{n}(driver):",
            f'    """{src_cls} -> {dst_cls} via {acc}."""',
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


def _flow_tests(model: TestModel, page_of: Dict[tuple, tuple]) -> str:
    """Behavioural tests driven through the Page Objects — the same coverage the flat
    style emits (form-filling, multi-step journeys, negative cases), rendered as page
    method calls instead of raw locators. One test per model case; steps whose element
    isn't a page field (system keys, waits, swipes) are skipped.

    A case is dropped rather than emitted when skipping cost it something: a TAP/TYPE
    with no page accessor is the interaction the case is about, and its assertions would
    then check a screen the test never reached (red on a working app); a case left with
    no ASSERT at all passes unconditionally under a name claiming it verified something."""
    used: set = set()
    seen_names: set = set()
    bodies: List[str] = []
    for case in model.cases:
        rendered: List[str] = []
        dropped_interaction = False
        asserted = False
        for step in case.steps:
            loc = page_of.get(_sel_key(step.selector)) if step.selector is not None else None
            if loc is None:
                if step.action in (ActionType.TAP, ActionType.TYPE):
                    dropped_interaction = True
                    break
                continue
            cls, acc = loc
            call = f"{cls}(driver).{acc}()"
            if step.action == ActionType.TYPE:
                used.add(cls)
                rendered.append(f"    {call}.send_keys({(step.text or '')!r})")
            elif step.action == ActionType.TAP:
                used.add(cls)
                rendered.append(f"    {call}.click()")
            elif step.action == ActionType.ASSERT:
                used.add(cls)
                asserted = True
                if step.assertion == AssertionType.NOT_VISIBLE:
                    rendered.append(f"    assert not {call}.is_displayed()")
                elif step.assertion == AssertionType.ENABLED:
                    rendered.append(f"    assert {call}.is_enabled()")
                elif step.assertion == AssertionType.TEXT_EQUALS and step.expected is not None:
                    rendered.append(f"    assert {call}.text == {step.expected!r}")
                else:  # VISIBLE (and any unmapped assertion) — the landmark check
                    rendered.append(f"    assert {call}.is_displayed()")
        if dropped_interaction or not asserted:
            continue
        name = snake(case.name) or "case"
        if name in seen_names:
            name = f"{name}_{len(seen_names)}"
        seen_names.add(name)
        desc = (case.description or case.name).replace('"', "'")
        bodies += [f"def test_{name}(driver):", f'    """{desc}"""', *rendered, ""]

    if not bodies:
        return ""
    lines = ['"""Flow tests — form-filling, journeys and negative cases, through the Page Objects."""', ""]
    for cls in sorted(used):
        lines.append(f"from pages.{snake(cls)} import {cls}")
    lines.append("")
    lines += bodies
    return "\n".join(lines)


def build_framework_kit(result: CrawlResult, model: TestModel, app_package: str) -> Dict[str, str]:
    """A proper pytest framework layout from a crawl (relative_path -> content)."""
    files: Dict[str, str] = {}
    page_files, page_of, pages = _page_objects(result, app_package)
    if not page_files:
        return files
    files["pages/__init__.py"] = ""
    files.update(page_files)
    files["conftest.py"] = _conftest(model)

    tests_written = False
    nav = _navigation_tests(result, app_package, pages)
    if nav:
        files["tests/test_navigation.py"] = nav
        tests_written = True
    # Behavioural parity with the flat style: form-filling, journeys, negative cases —
    # driven through the page objects, not just navigation smoke.
    flows = _flow_tests(model, page_of)
    if flows:
        files["tests/test_flows.py"] = flows
        tests_written = True
    if tests_written:
        files["tests/__init__.py"] = ""
    return files
