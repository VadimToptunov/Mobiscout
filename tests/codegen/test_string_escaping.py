"""Generated string literals must stay valid even for gnarly element text.

Jetpack Compose exposes multi-line paragraph text (with embedded newlines) as an
element's text; using it as a locator must not break the emitted source code.
"""

import ast

import pytest

from framework.codegen.emitters._java_common import java_str
from framework.codegen.emitters._js_common import js_str
from framework.codegen.emitters._kotlin_common import kotlin_str
from framework.codegen.emitters._python_common import py_str

NASTY = [
    "Published in: Android Developers\nRead more",  # newline (the JetNews bug)
    "tab\tseparated",
    'quote " and backslash \\ end',
    "carriage\r\nreturn",
]


@pytest.mark.parametrize("value", NASTY)
def test_py_str_is_valid_python_literal(value):
    # eval the emitted literal back and confirm it round-trips.
    assert ast.literal_eval(py_str(value)) == value


@pytest.mark.parametrize("value", NASTY)
def test_no_emitter_emits_raw_newline(value):
    # A raw newline/CR/tab inside the literal would break the line — none allowed.
    for rendered in (py_str(value), java_str(value), js_str(value), kotlin_str(value)):
        assert "\n" not in rendered and "\r" not in rendered and "\t" not in rendered
