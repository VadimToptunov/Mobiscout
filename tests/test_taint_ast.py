"""Tests for the AST-based Python taint analyzer (SAST)."""

import tempfile
import os
from pathlib import Path

from framework.security.sast.taint import TaintAnalyzer
from framework.security.sast.base import VulnerabilityType as VT


def _flows(code, suffix=".py"):
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
        f.write(code)
        f.close()
        path = Path(f.name)
    try:
        return TaintAnalyzer().analyze_file(path)
    finally:
        os.unlink(path)


def test_sql_injection_via_method_sink():
    flows = _flows("q = request.args['q']\ncursor.execute(q)\n")
    assert any(f.vulnerability_type is VT.SQL_INJECTION for f in flows)


def test_taint_propagates_through_assignments():
    flows = _flows("a = input()\nb = a\nos.system(b)\n")
    assert any(f.vulnerability_type is VT.COMMAND_INJECTION for f in flows)


def test_inline_source_into_sink():
    assert _flows("eval(input())\n")


def test_no_false_positive_on_substrings():
    # 'input'/'DES' appear as substrings but there is no real source->sink flow.
    assert _flows("describe = 'weak DES text'\nresult = compute(describe)\nprint('no input')\n") == []


def test_untainted_constant_not_flagged():
    assert _flows("q = 'SELECT 1'\ncursor.execute(q)\n") == []


def test_non_python_falls_back_to_patterns():
    flows = _flows("String user = getStringExtra(x);\nrawQuery(user);\n", suffix=".kt")
    assert any(f.vulnerability_type is VT.SQL_INJECTION for f in flows)
