"""
Shared Java rendering helpers (Appium Java client v9 API).

Maps the abstract IR selector strategies onto ``io.appium.java_client.AppiumBy``
factory calls. Extracted so an imperative TestNG/JUnit emitter and a future
Cucumber-JVM (BDD) emitter share one definition of "how a locator looks in
Java" and can never drift.
"""

from __future__ import annotations

from framework.codegen.emitters._escape import make_escaper
from framework.codegen.ir import Selector, SelectorStrategy
from framework.codegen.emitters._naming import ios_text_xpath, ua_escape

# Abstract strategy -> AppiumBy factory method (returns an org.openqa.selenium.By).
# TEXT maps to androidUIAutomator on Android; iOS has no such strategy and is
# rendered as an xpath() factory instead (see by_expr).
_BY_FACTORY = {
    SelectorStrategy.ID: "id",
    SelectorStrategy.ACCESSIBILITY_ID: "accessibilityId",
    SelectorStrategy.XPATH: "xpath",
    SelectorStrategy.CLASS_NAME: "className",
    SelectorStrategy.TEXT: "androidUIAutomator",
}


# Java double-quoted string literal, safely escaped. Control characters
# (newline/tab/cr) are escaped too, or multi-line element text would break the
# literal.
java_str = make_escaper('"')


def by_expr(sel: Selector, platform: str = "android") -> str:
    """Render an ``AppiumBy.x("value")`` expression for one selector."""
    if sel.strategy is SelectorStrategy.TEXT:
        if platform == "ios":
            # iOS has no UiAutomator text() — match @label/@name by XPath.
            return f"AppiumBy.xpath({java_str(ios_text_xpath(sel.value))})"
        value = java_str(f'new UiSelector().text("{ua_escape(sel.value)}")')
    else:
        value = java_str(sel.value)
    return f"AppiumBy.{_BY_FACTORY[sel.strategy]}({value})"


def by_array(sel: Selector, platform: str = "android") -> str:
    """Render the fallbacks as a Java ``By[]`` array literal (may be empty)."""
    items = ", ".join(by_expr(fb, platform) for fb in sel.fallbacks)
    return "new By[]{" + items + "}"


def by_list(sel: Selector, platform: str = "android") -> str:
    """Render primary + fallbacks as one Java ``By[]`` array literal. Used by the
    BDD LOCATORS registry where there is no separate 'primary' argument."""
    items = ", ".join(by_expr(s, platform) for s in [sel, *sel.fallbacks])
    return "new By[]{" + items + "}"
