"""
Shared Espresso rendering helpers (Android instrumented tests).

Espresso is NOT WebDriver: tests run on-device against the real view hierarchy
using Hamcrest ViewMatchers, there is no remote driver, no XPath, and no
runtime fallback chain. So the IR selector strategies map onto a *different*
surface here, and some IR concepts have no Espresso equivalent:

  * XPATH      -> unsupported (Espresso has no XPath); returns None so the
                  emitter can skip/annotate it.
  * fallbacks  -> Espresso resolves a single matcher; the primary is used and
                  fallbacks are not expressed at runtime.

This is the honest "separate model" the Espresso flavour requires.
"""

from __future__ import annotations

from typing import Optional

from framework.codegen.emitters._kotlin_common import kotlin_str
from framework.codegen.ir import Selector, SelectorStrategy, TestModel


def resource_id_segment(value: str) -> str:
    """Reduce an Appium resource-id to the R.id segment Espresso needs.
    e.g. ``com.example:id/user_field`` or ``user_field`` -> ``user_field``."""
    return value.split("/")[-1].split(":")[-1]


def matcher_expr(sel: Optional[Selector]) -> Optional[str]:
    """Render a Hamcrest ViewMatcher for one selector, or None if the strategy
    has no Espresso equivalent (XPath) or there is no selector."""
    if sel is None:
        return None
    s = sel.strategy
    if s is SelectorStrategy.ID:
        return f"withId(R.id.{resource_id_segment(sel.value)})"
    if s is SelectorStrategy.ACCESSIBILITY_ID:
        return f"withContentDescription({kotlin_str(sel.value)})"
    if s is SelectorStrategy.TEXT:
        return f"withText({kotlin_str(sel.value)})"
    if s is SelectorStrategy.CLASS_NAME:
        return f"withClassName(equalTo({kotlin_str(sel.value)}))"
    if s is SelectorStrategy.XPATH:
        return None
    raise ValueError(f"Unsupported selector strategy for Espresso: {s}")


def activity_class(model: TestModel) -> str:
    """The simple Activity class name for ActivityScenarioRule (from the IR's
    app_activity, defaulting to MainActivity)."""
    activity = model.app_activity or ".MainActivity"
    return activity.split(".")[-1] or "MainActivity"
