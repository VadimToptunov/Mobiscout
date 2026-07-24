"""Text-strategy selectors whose value contains a double-quote must not produce
an unbalanced UiAutomator expression (see docs/CODE_REVIEW.md §3). Regression for
the systemic raw-interpolation bug across the Python/Java/Kotlin/JS emitters.
"""

import ast

from framework.codegen.emitters._naming import ua_escape
from framework.codegen.emitters._python_common import locator_value
from framework.codegen.emitters._java_common import by_expr as java_by_expr
from framework.codegen.emitters._kotlin_common import by_expr as kotlin_by_expr
from framework.codegen.ir import Selector, SelectorStrategy


def test_ua_escape_escapes_quote_and_backslash():
    assert ua_escape('he said "hi"') == 'he said \\"hi\\"'
    assert ua_escape("a\\b") == "a\\\\b"
    assert ua_escape("clean") == "clean"  # identity for clean values


def _text_sel(value):
    return Selector(strategy=SelectorStrategy.TEXT, value=value)


def test_python_text_locator_is_valid_balanced_uiautomator():
    # locator_value returns a Python string *literal*; evaluate it and assert the
    # runtime UiAutomator expression has the inner quotes escaped (== balanced).
    out = locator_value(_text_sel('Say "hi"'))
    runtime = ast.literal_eval(out)
    assert runtime == 'new UiSelector().text("Say \\"hi\\"")'


def test_java_kotlin_text_expr_escape_quote():
    for fn in (java_by_expr, kotlin_by_expr):
        out = fn(_text_sel('a"b'))
        assert "UiSelector().text(" in out
        # the raw, unescaped sequence a"b must not survive into the expression
        assert 'a"b' not in out
