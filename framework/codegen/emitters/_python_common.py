"""
Shared Python rendering helpers.

The mapping from the abstract IR (selector strategies) onto the Appium Python
client is identical whether we emit an imperative pytest module or BDD step
definitions. Keeping it here lets both emitters share one source of truth for
"how a locator looks in Python", so the two output styles can never drift.
"""

from __future__ import annotations

from typing import List, Tuple

from framework.codegen.emitters._bdd_common import collect_targets, target_key  # noqa: F401
from framework.codegen.ir import Selector, SelectorStrategy

# Abstract strategy -> AppiumBy member used in generated Python code.
APPIUM_BY = {
    SelectorStrategy.ID: "AppiumBy.ID",
    SelectorStrategy.ACCESSIBILITY_ID: "AppiumBy.ACCESSIBILITY_ID",
    SelectorStrategy.XPATH: "AppiumBy.XPATH",
    SelectorStrategy.CLASS_NAME: "AppiumBy.CLASS_NAME",
    # Android text -> uiautomator selector; readable and stable enough for v1.
    SelectorStrategy.TEXT: "AppiumBy.ANDROID_UIAUTOMATOR",
}


def py_str(value: str) -> str:
    """Render a Python double-quoted string literal, safely escaped. Control
    characters (newline/tab/cr) are escaped too, or an element's multi-line text
    (common in Jetpack Compose paragraphs) would break the literal."""
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )
    return '"' + escaped + '"'


def locator_value(sel: Selector) -> str:
    """Produce the locator value string as it should appear in Python."""
    if sel.strategy is SelectorStrategy.TEXT:
        return py_str(f'new UiSelector().text("{sel.value}")')
    return py_str(sel.value)


def by_value(sel: Selector) -> str:
    """Render a ``(AppiumBy.X, "value")`` tuple for the _find helper."""
    return f"({APPIUM_BY[sel.strategy]}, {locator_value(sel)})"


def locator_chain(sel: Selector) -> str:
    """Render ``primary, [fallback, ...]`` flattened to a single list literal:
    ``[(AppiumBy.ID, "x"), (AppiumBy.XPATH, "//y")]`` — primary first."""
    items: List[str] = [by_value(sel)] + [by_value(fb) for fb in sel.fallbacks]
    return "[" + ", ".join(items) + "]"


def collect_locators(model) -> List[Tuple[str, str]]:
    """(target_key, python locator_chain) for every selector in the model.
    Targets/ordering come from the shared BDD helper; only the rendering of the
    chain is Python-specific."""
    return [(key, locator_chain(sel)) for key, sel in collect_targets(model)]
