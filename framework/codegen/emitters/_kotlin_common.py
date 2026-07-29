"""
Shared Kotlin rendering helpers (Appium Java client v9, used from Kotlin).

Kotlin drives Appium through the same ``io.appium.java_client.AppiumBy``
factories as Java; only the surrounding syntax differs (val/fun, no semicolons,
``arrayOf(...)`` instead of ``new By[]{}``, string templates). Extracted so an
imperative and a future BDD Kotlin emitter share one locator definition.
"""

from __future__ import annotations

from framework.codegen.emitters._escape import make_escaper
from framework.codegen.ir import Selector, SelectorStrategy
from framework.codegen.emitters._naming import ios_text_xpath, ua_escape

# Abstract strategy -> AppiumBy factory method (same names as the Java client).
# TEXT maps to androidUIAutomator on Android; iOS has no such strategy and is
# rendered as an xpath() factory instead (see by_expr).
_BY_FACTORY = {
    SelectorStrategy.ID: "id",
    SelectorStrategy.ACCESSIBILITY_ID: "accessibilityId",
    SelectorStrategy.XPATH: "xpath",
    SelectorStrategy.CLASS_NAME: "className",
    SelectorStrategy.TEXT: "androidUIAutomator",
}


# Kotlin double-quoted string literal, safely escaped. ``$`` is escaped too,
# since it begins a string template in Kotlin.
kotlin_str = make_escaper('"', extra={"$": "\\$"})


def by_expr(sel: Selector, platform: str = "android") -> str:
    """Render an ``AppiumBy.x("value")`` expression for one selector."""
    if sel.strategy is SelectorStrategy.TEXT:
        if platform == "ios":
            # iOS has no UiAutomator text() — match @label/@name by XPath.
            return f"AppiumBy.xpath({kotlin_str(ios_text_xpath(sel.value))})"
        value = kotlin_str(f'new UiSelector().text("{ua_escape(sel.value)}")')
    else:
        value = kotlin_str(sel.value)
    return f"AppiumBy.{_BY_FACTORY[sel.strategy]}({value})"


def by_array(sel: Selector, platform: str = "android") -> str:
    """Render the fallbacks as a Kotlin ``arrayOf(...)`` of By (may be empty)."""
    items = ", ".join(by_expr(fb, platform) for fb in sel.fallbacks)
    return f"arrayOf({items})"


def by_list(sel: Selector, platform: str = "android") -> str:
    """Render primary + fallbacks as one ``arrayOf(...)``. For a BDD LOCATORS map."""
    items = ", ".join(by_expr(s, platform) for s in [sel, *sel.fallbacks])
    return f"arrayOf({items})"
