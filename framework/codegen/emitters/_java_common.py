"""
Shared Java rendering helpers (Appium Java client v9 API).

Maps the abstract IR selector strategies onto ``io.appium.java_client.AppiumBy``
factory calls. Extracted so an imperative TestNG/JUnit emitter and a future
Cucumber-JVM (BDD) emitter share one definition of "how a locator looks in
Java" and can never drift.
"""

from __future__ import annotations

from framework.codegen.ir import Selector, SelectorStrategy

# Abstract strategy -> AppiumBy factory method (returns an org.openqa.selenium.By).
_BY_FACTORY = {
    SelectorStrategy.ID: "id",
    SelectorStrategy.ACCESSIBILITY_ID: "accessibilityId",
    SelectorStrategy.XPATH: "xpath",
    SelectorStrategy.CLASS_NAME: "className",
    SelectorStrategy.TEXT: "androidUIAutomator",
}


def java_str(value: str) -> str:
    """Render a Java double-quoted string literal, safely escaped. Control
    characters (newline/tab/cr) are escaped too, or multi-line element text
    would break the literal."""
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )
    return '"' + escaped + '"'


def by_expr(sel: Selector) -> str:
    """Render an ``AppiumBy.x("value")`` expression for one selector."""
    factory = _BY_FACTORY[sel.strategy]
    if sel.strategy is SelectorStrategy.TEXT:
        value = java_str(f'new UiSelector().text("{sel.value}")')
    else:
        value = java_str(sel.value)
    return f"AppiumBy.{factory}({value})"


def by_array(sel: Selector) -> str:
    """Render the fallbacks as a Java ``By[]`` array literal (may be empty)."""
    items = ", ".join(by_expr(fb) for fb in sel.fallbacks)
    return "new By[]{" + items + "}"


def by_list(sel: Selector) -> str:
    """Render primary + fallbacks as one Java ``By[]`` array literal. Used by the
    BDD LOCATORS registry where there is no separate 'primary' argument."""
    items = ", ".join(by_expr(s) for s in [sel, *sel.fallbacks])
    return "new By[]{" + items + "}"
