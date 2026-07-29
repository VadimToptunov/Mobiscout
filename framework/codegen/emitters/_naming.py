"""
Shared identifier-casing helpers for emitters.

Every emitter needs to turn a suite/case name into a language-appropriate
identifier (snake_case file, PascalClass, camelMethod, kebab-file). These were
copy-pasted across ~7 emitter modules; centralise them so the casing rules have
one definition.
"""

from __future__ import annotations


def snake(name: str) -> str:
    """``LoginFlow`` / ``Login flow`` -> ``login_flow``."""
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out).replace(" ", "_").replace("-", "_")


def kebab(name: str) -> str:
    """``LoginFlow`` -> ``login-flow``."""
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("-")
        out.append(ch.lower())
    return "".join(out).replace(" ", "-").replace("_", "-")


def camel(name: str) -> str:
    """``login_flow`` / ``login-flow`` -> ``loginFlow``."""
    parts = [p for p in name.replace("-", "_").split("_") if p]
    if not parts:
        return "test"
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def pascal(name: str) -> str:
    """``login_flow`` / ``login flow`` -> ``LoginFlow``."""
    parts = [p for p in name.replace("-", "_").replace(" ", "_").split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Generated"


def ua_escape(value: str) -> str:
    """Escape a value for embedding inside a UiAutomator expression string.

    UiAutomator selectors are strings like ``new UiSelector().text("...")`` that
    are *themselves* embedded in a host-language string literal (Python/Java/
    Kotlin/JS). The value therefore lives in two nested string contexts; this
    escapes the inner (UiAutomator) layer — backslash and double-quote — so a
    value such as ``he said "hi"`` cannot produce an unbalanced expression that
    Appium mis-parses. The host-language literal is escaped separately by
    ``py_str``/``java_str``/``kotlin_str``/``js_str``.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def ios_text_xpath(value: str) -> str:
    """An iOS-safe XPath that locates an element by its visible label / name.

    iOS/XCUITest has no UiAutomator ``text()`` strategy, so a ``TEXT`` selector
    must be rendered as an XPath matching the element's ``@label`` or ``@name``.
    Mirrors ``framework.crawler.to_codegen._xpath_by_label`` (used for the iOS
    text *fallback*) so the primary and fallback text locators agree.

    Quote-safe: uses whichever quote the value lacks, or ``concat()`` if it has
    both. The result is a plain XPath string; each language's own literal
    escaper wraps it for its host syntax.
    """
    if '"' not in value:
        lit = f'"{value}"'
    elif "'" not in value:
        lit = f"'{value}'"
    else:  # contains both quote kinds — build a concat() literal
        pieces = value.split('"')
        lit = "concat(" + ", '\"', ".join(f'"{p}"' for p in pieces) + ")"
    return f"//*[@label={lit} or @name={lit}]"
