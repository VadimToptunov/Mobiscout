"""
Shared Python rendering helpers.

The mapping from the abstract IR (selector strategies) onto the Appium Python
client is identical whether we emit an imperative pytest module or BDD step
definitions. Keeping it here lets both emitters share one source of truth for
"how a locator looks in Python", so the two output styles can never drift.
"""

from __future__ import annotations

from typing import List, Tuple

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
    """Render a Python double-quoted string literal, safely escaped."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


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


def target_key(sel: Selector) -> str:
    """A friendly, human-facing handle for a selector, used as the Gherkin
    target name and the LOCATORS registry key. Stable and readable."""
    return sel.description or sel.value


def collect_locators(model) -> List[Tuple[str, str]]:
    """Gather a de-duplicated, ordered list of (target_key, locator_chain) for
    every selector referenced in the model. Drives the BDD LOCATORS registry."""
    seen = {}
    order: List[str] = []
    for case in model.cases:
        for step in case.steps:
            if step.selector is None:
                continue
            key = target_key(step.selector)
            if key not in seen:
                seen[key] = locator_chain(step.selector)
                order.append(key)
    return [(k, seen[k]) for k in order]
