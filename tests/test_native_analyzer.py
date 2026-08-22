"""The optional Rust-acceleration seam (framework/analyzers/native.py).

The native wheel isn't installed in CI's Python job, so these mostly exercise the
pure-Python fallback (which must be correct on its own) and simulate the Rust core with
a fake module to prove the seam uses it when present and degrades to Python on error.
"""

import framework.analyzers.native as native
from framework.analyzers.native import SourceComplexity, analyze_source_complexity, backend_name


def test_backend_is_python_without_the_wheel():
    # The wheel isn't installed here, so the fallback backend is active.
    assert backend_name() == "python"
    assert native.native_available() is False


def test_python_fallback_counts_functions_classes_and_branches():
    source = (
        "class A:\n"
        "    def f(self, x):\n"
        "        if x > 0 and x < 10:\n"
        "            for i in range(x):\n"
        "                pass\n"
        "        return x\n"
        "    def g(self):\n"
        "        try:\n"
        "            pass\n"
        "        except ValueError:\n"
        "            pass\n"
    )
    c = analyze_source_complexity(source, "python")
    assert c.function_count == 2
    assert c.class_count == 1
    # base 1 + if + for + (bool-op adds 1) + except = 5
    assert c.cyclomatic_complexity == 5
    assert c.max_nesting_depth >= 2  # if -> for
    assert c.lines_of_code == len([ln for ln in source.splitlines() if ln.strip()])


def test_python_fallback_on_syntax_error_uses_heuristic():
    # Not valid Python — must not raise; falls back to the keyword heuristic.
    c = analyze_source_complexity("def (((", "python")
    assert isinstance(c, SourceComplexity)
    assert c.cyclomatic_complexity >= 1


def test_heuristic_handles_a_non_python_language():
    kotlin = (
        "class Login {\n"
        "    fun submit(u: String) {\n"
        "        if (u.isNotEmpty() && u.length > 3) { doLogin() }\n"
        "        for (c in u) { }\n"
        "    }\n"
        "}\n"
    )
    c = analyze_source_complexity(kotlin, "kotlin")
    assert c.function_count >= 1 and c.class_count >= 1
    assert c.cyclomatic_complexity > 1  # if + for + &&


def test_risk_level_bands():
    assert SourceComplexity(5, 5, 1, 10, 1, 1).risk_level == "low"
    assert SourceComplexity(12, 5, 1, 10, 1, 1).risk_level == "medium"
    assert SourceComplexity(25, 5, 1, 10, 1, 1).risk_level == "high"


class _FakeMetrics:
    cyclomatic_complexity = 7
    cognitive_complexity = 9
    max_nesting_depth = 3
    lines_of_code = 42
    function_count = 4
    class_count = 2


class _FakeAnalyzer:
    def analyze_source(self, source, language):
        return _FakeMetrics()


class _FakeCore:
    RustAstAnalyzer = _FakeAnalyzer


def test_native_core_is_used_when_present(monkeypatch):
    monkeypatch.setattr(native, "_native_core", lambda: _FakeCore())
    assert native.backend_name() == "rust"
    c = analyze_source_complexity("whatever", "swift")
    assert (c.cyclomatic_complexity, c.function_count, c.class_count) == (7, 4, 2)
    assert c.lines_of_code == 42


def test_native_error_degrades_to_python(monkeypatch):
    class _Boom:
        class RustAstAnalyzer:
            def analyze_source(self, source, language):
                raise RuntimeError("abi mismatch")

    monkeypatch.setattr(native, "_native_core", lambda: _Boom())
    # Falls back to the Python analyzer instead of raising.
    c = analyze_source_complexity("def f():\n    return 1\n", "python")
    assert c.function_count == 1
