"""
ir_builder — turn discovered app structure into a language-agnostic TestModel.

This is the seam between "explore" (crawler/flow output) and "automate"
(emitters). It knows about app models (Screen/UIElement) but nothing about
target languages. Once a TestModel exists, any emitter can render it.

v1 produces a "smoke" test per screen: launch the app and assert each
interactive element on the screen is visible. As the crawler matures, this
will grow to walk real flow paths (FlowGraph) into multi-step cases.
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
from framework.core.engine import Screen, UIElement


def _selector_for(element: UIElement) -> Selector:
    """Pick the most stable available locator, with the rest as fallbacks.

    Order mirrors selector_scorer's stability ranking: accessibility id and
    resource id beat xpath. This keeps generated tests resilient and lets
    self-healing fall back gracefully.
    """
    candidates: List[Selector] = []
    if element.accessibility_id:
        candidates.append(Selector(SelectorStrategy.ACCESSIBILITY_ID, element.accessibility_id, score=0.95))
    if element.id:
        candidates.append(Selector(SelectorStrategy.ID, element.id, score=0.90))
    if element.label:
        candidates.append(Selector(SelectorStrategy.TEXT, element.label, score=0.60))
    if element.xpath:
        candidates.append(Selector(SelectorStrategy.XPATH, element.xpath, score=0.30))

    if not candidates:
        raise ValueError(f"Element {element.id!r} has no usable locator")

    primary, *rest = candidates
    primary.fallbacks = rest
    return primary


def _case_name(screen: Screen) -> str:
    base = (screen.name or screen.id or "screen").strip().lower()
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in base)
    cleaned = "_".join(filter(None, cleaned.split("_")))
    return cleaned or "screen"


def build_smoke_model(
    screens: List[Screen],
    app_package: str,
    suite_name: str = "SmokeFlow",
    platform: Platform = Platform.ANDROID,
    app_activity: Optional[str] = None,
) -> TestModel:
    """Build a TestModel that launches the app and asserts each screen's
    interactive elements are visible. One TestCase per screen."""
    cases: List[TestCase] = []
    for screen in screens:
        steps: List[Step] = [Step(ActionType.LAUNCH, description=f"Open {screen.name or screen.id}")]
        for element in screen.find_interactive_elements():
            try:
                selector = _selector_for(element)
            except ValueError:
                continue  # skip elements we cannot locate
            steps.append(
                Step(
                    ActionType.ASSERT,
                    selector=selector,
                    assertion=AssertionType.VISIBLE,
                    description=f"{element.type} {element.label or element.id} is visible",
                )
            )
        if len(steps) > 1:  # only emit a case that actually checks something
            cases.append(
                TestCase(name=_case_name(screen), steps=steps, description=f"Smoke test for {screen.name or screen.id}")
            )

    return TestModel(
        name=suite_name,
        app_package=app_package,
        platform=platform,
        app_activity=app_activity,
        cases=cases,
        description="Auto-generated smoke suite from discovered screens.",
    )
