"""
Bridge: crawler output -> codegen IR.

Turns a CrawlResult (discovered screens + elements) into a codegen TestModel so
the paths the crawler explored can be emitted as tests in any target language.
This is the "explore -> automate" seam that closes the golden path:

    AppCrawler.crawl() -> CrawlResult -> build_test_model -> emitter -> test code
"""

from __future__ import annotations

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
from framework.crawler.app_crawler import CrawlElement, CrawlResult

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


def _case_name(index: int, element_count: int) -> str:
    return f"screen_{index + 1}"


def build_test_model(
    result: CrawlResult,
    app_package: str,
    suite_name: str = "CrawlFlow",
    app_activity: Optional[str] = None,
) -> TestModel:
    """Build a codegen TestModel from a crawl: one smoke case per discovered
    screen that launches the app and asserts each interactive element is visible."""
    cases: List[TestCase] = []
    for index, screen in enumerate(result.screens.values()):
        steps: List[Step] = [Step(ActionType.LAUNCH, description="Open app")]
        # Assert every element with a usable locator (not just the clickable
        # ones): in Jetpack Compose the tappable node is often empty while its
        # visible text/description lives on a sibling node.
        seen = set()
        for element in screen.elements:
            selector = _selector_for(element)
            if selector is None or selector.value in seen:
                continue
            seen.add(selector.value)
            if selector is None:
                continue
            steps.append(
                Step(
                    ActionType.ASSERT,
                    selector=selector,
                    assertion=AssertionType.VISIBLE,
                    description=f"{element.label or element.class_name} is visible",
                )
            )
        if len(steps) > 1:
            cases.append(
                TestCase(
                    name=_case_name(index, len(steps)),
                    steps=steps,
                    description=f"Smoke test for discovered screen {index + 1}",
                )
            )

    return TestModel(
        name=suite_name,
        app_package=app_package,
        platform=Platform.ANDROID,
        app_activity=app_activity,
        cases=cases,
        description="Auto-generated from an autonomous crawl.",
    )
