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
from framework.codegen.emitters._escape import make_escaper
from framework.codegen.ir import Selector, SelectorStrategy, TestModel
from framework.codegen.emitters._naming import ios_text_xpath, ua_escape
from framework.codegen.keys import keycode  # noqa: F401  (re-exported for emitter filters)

# Abstract strategy -> AppiumBy member used in generated Python code.
APPIUM_BY = {
    SelectorStrategy.ID: "AppiumBy.ID",
    SelectorStrategy.ACCESSIBILITY_ID: "AppiumBy.ACCESSIBILITY_ID",
    SelectorStrategy.XPATH: "AppiumBy.XPATH",
    SelectorStrategy.CLASS_NAME: "AppiumBy.CLASS_NAME",
    # Android text -> uiautomator selector; readable and stable enough for v1.
    # iOS has no UiAutomator; a TEXT selector is rendered as an XPath-by-label
    # instead (see by_value / locator_value), so this entry is Android-only.
    SelectorStrategy.TEXT: "AppiumBy.ANDROID_UIAUTOMATOR",
}


# The Android keycode table + `keycode` filter live in framework.codegen.keys
# (single source of truth); `keycode` is re-exported above for the emitters that
# register it as a Jinja filter.


# Python double-quoted string literal, safely escaped. Control characters
# (newline/tab/cr) are escaped too, or an element's multi-line text (common in
# Jetpack Compose paragraphs) would break the literal.
py_str = make_escaper('"')


def locator_value(sel: Selector, platform: str = "android") -> str:
    """Produce the locator value string as it should appear in Python."""
    if sel.strategy is SelectorStrategy.TEXT:
        if platform == "ios":
            # iOS has no UiAutomator text() strategy — match @label/@name by XPath.
            return py_str(ios_text_xpath(sel.value))
        # ua_escape handles the inner UiAutomator string layer; py_str the outer
        # Python literal (two nested string contexts).
        return py_str(f'new UiSelector().text("{ua_escape(sel.value)}")')
    return py_str(sel.value)


def by_value(sel: Selector, platform: str = "android") -> str:
    """Render a ``(AppiumBy.X, "value")`` tuple for the _find helper."""
    strategy = SelectorStrategy.XPATH if (sel.strategy is SelectorStrategy.TEXT and platform == "ios") else sel.strategy
    return f"({APPIUM_BY[strategy]}, {locator_value(sel, platform)})"


def locator_chain(sel: Selector, platform: str = "android") -> str:
    """Render ``primary, [fallback, ...]`` flattened to a single list literal:
    ``[(AppiumBy.ID, "x"), (AppiumBy.XPATH, "//y")]`` — primary first."""
    items: List[str] = [by_value(sel, platform)] + [by_value(fb, platform) for fb in sel.fallbacks]
    return "[" + ", ".join(items) + "]"


def collect_locators(model: TestModel) -> List[Tuple[str, str]]:
    """(target_key, python locator_chain) for every selector in the model.
    Targets/ordering come from the shared BDD helper; only the rendering of the
    chain is Python-specific."""
    platform = model.platform.value
    return [(key, locator_chain(sel, platform)) for key, sel in collect_targets(model)]
