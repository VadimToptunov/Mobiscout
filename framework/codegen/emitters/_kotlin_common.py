"""
Shared Kotlin rendering helpers (Appium Java client v9, used from Kotlin).

Kotlin drives Appium through the same ``io.appium.java_client.AppiumBy``
factories as Java; only the surrounding syntax differs (val/fun, no semicolons,
``arrayOf(...)`` instead of ``new By[]{}``, string templates). Extracted so an
imperative and a future BDD Kotlin emitter share one locator definition.
"""

from __future__ import annotations

from framework.codegen.ir import Selector, SelectorStrategy

# Abstract strategy -> AppiumBy factory method (same names as the Java client).
_BY_FACTORY = {
    SelectorStrategy.ID: "id",
    SelectorStrategy.ACCESSIBILITY_ID: "accessibilityId",
    SelectorStrategy.XPATH: "xpath",
    SelectorStrategy.CLASS_NAME: "className",
    SelectorStrategy.TEXT: "androidUIAutomator",
}


def kotlin_str(value: str) -> str:
    """Render a Kotlin double-quoted string literal, safely escaped. ``$`` is
    escaped too, since it begins a string template in Kotlin."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return '"' + escaped + '"'


def by_expr(sel: Selector) -> str:
    """Render an ``AppiumBy.x("value")`` expression for one selector."""
    factory = _BY_FACTORY[sel.strategy]
    if sel.strategy is SelectorStrategy.TEXT:
        value = kotlin_str(f'new UiSelector().text("{sel.value}")')
    else:
        value = kotlin_str(sel.value)
    return f"AppiumBy.{factory}({value})"


def by_array(sel: Selector) -> str:
    """Render the fallbacks as a Kotlin ``arrayOf(...)`` of By (may be empty)."""
    items = ", ".join(by_expr(fb) for fb in sel.fallbacks)
    return f"arrayOf({items})"


def by_list(sel: Selector) -> str:
    """Render primary + fallbacks as one ``arrayOf(...)``. For a BDD LOCATORS map."""
    items = ", ".join(by_expr(s) for s in [sel, *sel.fallbacks])
    return f"arrayOf({items})"
