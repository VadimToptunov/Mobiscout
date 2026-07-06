"""
Bridge: crawler output -> codegen IR + audits.

Turns a CrawlResult into a comprehensive codegen TestModel (not just a smoke
suite): per-screen state checks, navigation/interaction flows from the recorded
transitions, plus a standalone accessibility audit. This is the
"explore -> automate" seam that closes the golden path:

    AppCrawler.crawl() -> CrawlResult -> build_test_model -> emitter -> test code
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from framework.codegen.ir import (
    ActionType,
    AssertionType,
    Platform,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen


def _xpath_by_label(value: str) -> str:
    """An iOS-safe XPath that locates an element by its visible label / name.
    Quote-safe: uses whichever quote the value lacks, or concat() if it has both."""
    if '"' not in value:
        lit = f'"{value}"'
    elif "'" not in value:
        lit = f"'{value}'"
    else:  # contains both quote kinds — build a concat() literal
        pieces = value.split('"')
        lit = "concat(" + ", '\"', ".join(f'"{p}"' for p in pieces) + ")"
    return f"//*[@label={lit} or @name={lit}]"


def _selector_for(element: CrawlElement, platform: str = "android") -> Optional[Selector]:
    """Ranked IR selector (primary + fallbacks) from a crawled element.

    Accessibility-id and resource-id map identically on both platforms, but a
    *visible-text* locator does not: Android wants a uiautomator ``text()``
    selector, whereas iOS has no such thing — it must match the element's
    ``label`` via XPath. So the text tier is rendered per platform.
    """
    candidates: List[Selector] = []
    label = element.label
    cd = (element.content_desc or "").strip()
    if cd:
        candidates.append(Selector(SelectorStrategy.ACCESSIBILITY_ID, cd, score=0.95, description=label))
    rid = (element.resource_id or "").strip()
    if rid:
        candidates.append(Selector(SelectorStrategy.ID, rid, score=0.90, description=label))
    txt = (element.text or "").strip()
    if txt:
        if platform == "ios":
            candidates.append(Selector(SelectorStrategy.XPATH, _xpath_by_label(txt), score=0.60, description=label))
        else:
            candidates.append(Selector(SelectorStrategy.TEXT, txt, score=0.60, description=label))
    if not candidates:
        return None
    primary, *rest = candidates
    primary.fallbacks = rest
    return primary


def _contains(outer: CrawlElement, inner: CrawlElement) -> bool:
    ox1, oy1, ox2, oy2 = outer.bounds
    ix1, iy1, ix2, iy2 = inner.bounds
    return ox1 <= ix1 and oy1 <= iy1 and ix2 <= ox2 and iy2 <= oy2 and inner.bounds != outer.bounds


def selector_for(
    element: CrawlElement, siblings: Optional[List[CrawlElement]] = None, platform: str = "android"
) -> Optional[Selector]:
    """Locator for an element, with a Jetpack Compose fallback.

    In Compose the clickable node is often an unlabelled wrapper while the
    visible text sits on a non-clickable child, so a direct locator is empty.
    When that happens for a clickable element, borrow the locator of the
    innermost labelled element contained within its bounds — tapping that child
    (inside the clickable) triggers the same action.
    """
    own = _selector_for(element, platform)
    if own is not None or not element.clickable or not siblings:
        return own
    best: Optional[Selector] = None
    best_area: Optional[int] = None
    for other in siblings:
        if other is element or not _contains(element, other):
            continue
        sel = _selector_for(other, platform)
        if sel is None:
            continue
        x1, y1, x2, y2 = other.bounds
        area = (x2 - x1) * (y2 - y1)
        if best_area is None or area < best_area:
            best, best_area = sel, area
    return best


def _owned(screen: CrawlScreen, app_package: str) -> List[CrawlElement]:
    return [e for e in screen.elements if e.package in ("", app_package)]


def _screen_cases(index: int, screen: CrawlScreen, app_package: str) -> Optional[TestCase]:
    """A per-screen state case: every locatable element is visible, and every
    interactive one is also enabled (interactability, not just presence)."""
    steps: List[Step] = [Step(ActionType.LAUNCH, description="Open app")]
    seen = set()
    owned = _owned(screen, app_package)
    for element in owned:
        selector = selector_for(element, owned, screen.platform)
        if selector is None or selector.value in seen:
            continue
        seen.add(selector.value)
        label = element.label or element.class_name
        steps.append(
            Step(
                ActionType.ASSERT, selector=selector, assertion=AssertionType.VISIBLE, description=f"{label} is visible"
            )
        )
        if element.clickable:
            steps.append(
                Step(
                    ActionType.ASSERT,
                    selector=selector,
                    assertion=AssertionType.ENABLED,
                    description=f"{label} is enabled",
                )
            )
    if len(steps) == 1:
        return None
    return TestCase(
        name=f"screen_{index + 1}_state", steps=steps, description=f"State checks for discovered screen {index + 1}"
    )


def _navigation_cases(result: CrawlResult, app_package: str) -> List[TestCase]:
    """Functional flows: from the start screen, tap an element and assert we
    reached the destination screen (a distinctive element there is visible)."""
    if not result.screens:
        return []
    start_fp = next(iter(result.screens))
    cases: List[TestCase] = []
    seen_taps = set()
    from_screen = result.screens.get(start_fp)
    from_elements = _owned(from_screen, app_package) if from_screen else []
    from_platform = from_screen.platform if from_screen else "android"
    for from_fp, element, to_fp in result.transitions:
        if from_fp != start_fp or to_fp == start_fp:
            continue  # only depth-1, real navigations (path reconstruction is future work)
        tap = selector_for(element, from_elements, from_platform)
        if tap is None or tap.value in seen_taps:
            continue
        target = result.screens.get(to_fp)
        target_elements = _owned(target, app_package) if target else []
        target_platform = target.platform if target else "android"
        landmark = next(
            (s for s in (selector_for(e, target_elements, target_platform) for e in target_elements) if s), None
        )
        if landmark is None:
            continue
        seen_taps.add(tap.value)
        steps = [
            Step(ActionType.LAUNCH, description="Open app"),
            Step(ActionType.TAP, selector=tap, description=f"Tap {element.label or element.class_name}"),
            Step(
                ActionType.ASSERT,
                selector=landmark,
                assertion=AssertionType.VISIBLE,
                description="Destination screen is shown",
            ),
        ]
        cases.append(
            TestCase(
                name=f"navigate_{len(cases) + 1}",
                steps=steps,
                description=f"Tapping {element.label or element.class_name} navigates onward",
            )
        )
    return cases


def build_test_model(
    result: CrawlResult,
    app_package: str,
    suite_name: str = "CrawlFlow",
    app_activity: Optional[str] = None,
) -> TestModel:
    """Comprehensive TestModel from a crawl: per-screen state checks (visible +
    enabled) plus navigation flows from the recorded transitions."""
    cases: List[TestCase] = []
    for index, screen in enumerate(result.screens.values()):
        case = _screen_cases(index, screen, app_package)
        if case is not None:
            cases.append(case)
    cases.extend(_navigation_cases(result, app_package))

    # Multi-step, model-based paths through the interaction graph (lazy import:
    # graph.py imports this module, so importing it here avoids a cycle).
    from framework.crawler.graph import multi_step_cases

    cases.extend(multi_step_cases(result, app_package))

    # The suite's platform follows the crawled screens (any iOS screen -> iOS),
    # so the emitters pick the right Appium client and text locators.
    is_ios = any(s.platform == "ios" for s in result.screens.values())

    return TestModel(
        name=suite_name,
        app_package=app_package,
        platform=Platform.IOS if is_ios else Platform.ANDROID,
        app_activity=app_activity,
        cases=cases,
        description="Auto-generated from an autonomous crawl (state + navigation).",
    )


@dataclass
class AccessibilityFinding:
    screen_index: int
    class_name: str
    bounds: str
    issue: str


def audit_accessibility(result: CrawlResult, app_package: str = "") -> List[AccessibilityFinding]:
    """Flag interactive elements a screen reader cannot announce: clickable with
    no accessible label (no content-desc / text / resource-id)."""
    findings: List[AccessibilityFinding] = []
    for index, screen in enumerate(result.screens.values()):
        for element in _owned(screen, app_package) if app_package else screen.elements:
            if not element.clickable:
                continue
            has_label = element.content_desc or element.text or element.resource_id
            if not has_label:
                findings.append(
                    AccessibilityFinding(
                        screen_index=index + 1,
                        class_name=element.class_name,
                        bounds=str(element.bounds),
                        issue="clickable element has no accessible label (content-desc/text/id)",
                    )
                )
    return findings
