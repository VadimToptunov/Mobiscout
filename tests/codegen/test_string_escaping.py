"""Generated string literals must stay valid even for gnarly element text.

Jetpack Compose exposes multi-line paragraph text (with embedded newlines) as an
element's text; using it as a locator must not break the emitted source code.
"""

import ast

import pytest

from framework.codegen.emitters._escape import make_escaper
from framework.codegen.emitters._java_common import java_str
from framework.codegen.emitters._js_common import js_str
from framework.codegen.emitters._kotlin_common import kotlin_str
from framework.codegen.emitters._python_common import py_str

NASTY = [
    "Published in: Android Developers\nRead more",  # newline (the JetNews bug)
    "tab\tseparated",
    'quote " and backslash \\ end',
    "carriage\r\nreturn",
    "single ' quote",
    "kotlin $template and ${expr}",
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


# --- item 2: the shared make_escaper must reproduce each language's escaper
# byte-for-byte. Reference implementations below are the pre-refactor logic,
# transcribed verbatim; the extracted functions must equal them for every input.


def _ref_py(value):
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )
    return '"' + escaped + '"'


def _ref_java(value):
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )
    return '"' + escaped + '"'


def _ref_js(value):
    escaped = (
        value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )
    return "'" + escaped + "'"


def _ref_kotlin(value):
    if value is None:
        value = ""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return '"' + escaped + '"'


@pytest.mark.parametrize("value", NASTY)
def test_make_escaper_matches_legacy_per_language(value):
    assert py_str(value) == _ref_py(value)
    assert java_str(value) == _ref_java(value)
    assert js_str(value) == _ref_js(value)
    assert kotlin_str(value) == _ref_kotlin(value)


def test_kotlin_escaper_handles_none():
    # kotlin_str historically accepted None (rendered as an empty literal); the
    # shared escaper must preserve that.
    assert kotlin_str(None) == '""'


def test_make_escaper_quote_and_extras_are_wired():
    # Sanity on the factory itself: the delimiting quote is escaped, extras are
    # applied, and a clean value is only wrapped.
    single = make_escaper("'")
    assert single("it's") == "'it\\'s'"
    dollar = make_escaper('"', extra={"$": "\\$"})
    assert dollar("a$b") == '"a\\$b"'
    assert make_escaper('"')("clean") == '"clean"'
