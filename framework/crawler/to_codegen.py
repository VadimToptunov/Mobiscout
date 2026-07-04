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

# Stability ranking, mirroring the app-model adapter / selector_scorer.
_RANKED = (
    (lambda e: e.content_desc, SelectorStrategy.ACCESSIBILITY_ID, 0.95),
    (lambda e: e.resource_id, SelectorStrategy.ID, 0.90),
    (lambda e: e.text, SelectorStrategy.TEXT, 0.60),
)


def _selector_for(element: CrawlElement) -> Optional[Selector]:
    """Ranked IR selector (primary + fallbacks) from a crawled element."""
    candidates: List[Selector] = []
    for getter, strategy, score in _RANKED:
        value = (getter(element) or "").strip()
        if value:
            candidates.append(Selector(strategy, value, score=score, description=element.label))
    if not candidates:
        return None
    primary, *rest = candidates
    primary.fallbacks = rest
    return primary


def _contains(outer: CrawlElement, inner: CrawlElement) -> bool:
    ox1, oy1, ox2, oy2 = outer.bounds
    ix1, iy1, ix2, iy2 = inner.bounds
    return ox1 <= ix1 and oy1 <= iy1 and ix2 <= ox2 and iy2 <= oy2 and inner.bounds != outer.bounds


def selector_for(element: CrawlElement, siblings: Optional[List[CrawlElement]] = None) -> Optional[Selector]:
    """Locator for an element, with a Jetpack Compose fallback.

    In Compose the clickable node is often an unlabelled wrapper while the
    visible text sits on a non-clickable child, so a direct locator is empty.
    When that happens for a clickable element, borrow the locator of the
    innermost labelled element contained within its bounds — tapping that child
    (inside the clickable) triggers the same action.
    """
    own = _selector_for(element)
    if own is not None or not element.clickable or not siblings:
        return own
    best: Optional[Selector] = None
    best_area: Optional[int] = None
    for other in siblings:
        if other is element or not _contains(element, other):
            continue
        sel = _selector_for(other)
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
        selector = selector_for(element, owned)
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
    for from_fp, element, to_fp in result.transitions:
        if from_fp != start_fp or to_fp == start_fp:
            continue  # only depth-1, real navigations (path reconstruction is future work)
        tap = selector_for(element, from_elements)
        if tap is None or tap.value in seen_taps:
            continue
        target = result.screens.get(to_fp)
        target_elements = _owned(target, app_package) if target else []
        landmark = next((s for s in (selector_for(e, target_elements) for e in target_elements) if s), None)
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

    return TestModel(
        name=suite_name,
        app_package=app_package,
        platform=Platform.ANDROID,
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
