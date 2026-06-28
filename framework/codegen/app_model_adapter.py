"""
Adapter: framework.model.AppModel (the canonical, pydantic app model) -> codegen IR.

This is the bridge that lets the codegen pipeline (and the CLI) generate test
code in any registered language from a recorded app model. It mirrors
ir_builder.build_smoke_model but consumes the richer pydantic model.Screen /
model.Element / model.Selector instead of the legacy core.engine dataclasses.

v1 produces a smoke suite: per screen, launch the app and assert each element
with a usable locator is visible. As flows mature this grows into real paths.
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
from framework.model.app_model import AppModel
from framework.model.element import Element

# model.Selector encodes locators as "strategy:value" strings; map the prefix
# to an abstract IR strategy.
_PREFIX_TO_STRATEGY = {
    "id": SelectorStrategy.ID,
    "resource-id": SelectorStrategy.ID,
    "accessibility": SelectorStrategy.ACCESSIBILITY_ID,
    "accessibility_id": SelectorStrategy.ACCESSIBILITY_ID,
    "xpath": SelectorStrategy.XPATH,
    "class": SelectorStrategy.CLASS_NAME,
    "class_name": SelectorStrategy.CLASS_NAME,
    "text": SelectorStrategy.TEXT,
}

# Stability scores mirror selector_scorer's ranking.
_STRATEGY_SCORE = {
    SelectorStrategy.ACCESSIBILITY_ID: 0.95,
    SelectorStrategy.ID: 0.90,
    SelectorStrategy.TEXT: 0.60,
    SelectorStrategy.CLASS_NAME: 0.50,
    SelectorStrategy.XPATH: 0.30,
}


def _parse_locator(raw: str, description: str) -> Optional[Selector]:
    """Parse a model.Selector locator string ("id:foo", "accessibility:bar",
    a bare xpath, ...) into an IR Selector."""
    if not raw:
        return None
    prefix, sep, value = raw.partition(":")
    strategy = _PREFIX_TO_STRATEGY.get(prefix.strip().lower()) if sep else None
    if strategy is None:
        # No recognised prefix: treat a leading "/" as xpath, else an id.
        strategy = SelectorStrategy.XPATH if raw.startswith("/") else SelectorStrategy.ID
        value = raw
    return Selector(
        strategy=strategy,
        value=value.strip(),
        score=_STRATEGY_SCORE.get(strategy, 0.5),
        description=description,
    )


def _selector_for(element: Element) -> Optional[Selector]:
    """Build a ranked IR Selector (primary + fallbacks) from a model.Element."""
    sel = element.selector
    candidates: List[Selector] = []

    if sel.test_id:
        candidates.append(Selector(SelectorStrategy.ACCESSIBILITY_ID, sel.test_id, score=0.95, description=element.id))
    for raw in (sel.android, sel.xpath, *sel.android_fallback):
        parsed = _parse_locator(raw, element.id) if raw else None
        if parsed is not None:
            candidates.append(parsed)

    if not candidates:
        return None

    # Rank by stability, drop duplicate (strategy, value) pairs.
    seen = set()
    ranked: List[Selector] = []
    for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
        key = (cand.strategy, cand.value)
        if key in seen:
            continue
        seen.add(key)
        ranked.append(cand)

    primary, *rest = ranked
    primary.fallbacks = rest
    return primary


def _case_name(screen_name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in screen_name.strip().lower())
    return "_".join(filter(None, cleaned.split("_"))) or "screen"


def build_smoke_model(
    app_model: AppModel,
    app_package: str,
    suite_name: str = "SmokeFlow",
    app_activity: Optional[str] = None,
) -> TestModel:
    """Build a smoke TestModel from a recorded AppModel: one TestCase per screen
    that launches the app and asserts each locatable element is visible."""
    cases: List[TestCase] = []
    for screen in app_model.screens.values():
        steps: List[Step] = [Step(ActionType.LAUNCH, description=f"Open {screen.name}")]
        for element in screen.elements:
            selector = _selector_for(element)
            if selector is None:
                continue
            steps.append(
                Step(
                    ActionType.ASSERT,
                    selector=selector,
                    assertion=AssertionType.VISIBLE,
                    description=f"{element.type.value} {element.id} is visible",
                )
            )
        if len(steps) > 1:  # only emit a case that checks something
            cases.append(
                TestCase(
                    name=_case_name(screen.name),
                    steps=steps,
                    description=f"Smoke test for {screen.name}",
                )
            )

    return TestModel(
        name=suite_name,
        app_package=app_package,
        platform=Platform.ANDROID,
        app_activity=app_activity,
        cases=cases,
        description="Auto-generated smoke suite from the recorded app model.",
    )
