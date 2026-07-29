"""
Shared JavaScript rendering helpers (WebdriverIO mobile selectors).

Maps the abstract IR selector strategies onto WebdriverIO's documented mobile
selector strings. Resource id / class name / text all go through Android
uiAutomator so the mapping is unambiguous and provably correct (no guessing at
shorthand prefixes); accessibility id and xpath use WebdriverIO's native
``~`` and raw-xpath forms.

Extracted so an imperative spec emitter and a future Cucumber.js (BDD) emitter
share one definition of "how a locator looks in WebdriverIO".
"""

from __future__ import annotations

from framework.codegen.emitters._escape import make_escaper
from framework.codegen.ir import Selector, SelectorStrategy
from framework.codegen.emitters._naming import ua_escape

# Single-quoted JS string literal, safely escaped. Single quotes keep the common
# double-quoted uiAutomator expressions readable.
js_str = make_escaper("'")


def _wdio_selector(sel: Selector) -> str:
    """The raw WebdriverIO selector string for one selector (pre-escaping)."""
    s = sel.strategy
    if s is SelectorStrategy.ACCESSIBILITY_ID:
        return f"~{sel.value}"
    if s is SelectorStrategy.XPATH:
        return sel.value
    if s is SelectorStrategy.ID:
        return f'android=new UiSelector().resourceId("{ua_escape(sel.value)}")'
    if s is SelectorStrategy.CLASS_NAME:
        return f'android=new UiSelector().className("{ua_escape(sel.value)}")'
    if s is SelectorStrategy.TEXT:
        return f'android=new UiSelector().text("{ua_escape(sel.value)}")'
    raise ValueError(f"Unsupported selector strategy for WebdriverIO: {s}")


def selector_array(sel: Selector) -> str:
    """Render ``['primary', 'fallback', ...]`` as a JS array literal."""
    items = [js_str(_wdio_selector(sel))] + [js_str(_wdio_selector(fb)) for fb in sel.fallbacks]
    return "[" + ", ".join(items) + "]"
