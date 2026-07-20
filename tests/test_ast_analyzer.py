"""Deep AST analysis: complexity metric extraction from Python source trees.

The ASTAnalyzer walks a directory of ``*.py`` files, parses each with the stdlib
``ast`` module, and computes per-function cyclomatic/cognitive complexity,
nesting depth, and various counts (returns, branches, loops, parameters). These
tests write real Python snippets to ``tmp_path`` and assert the derived metrics,
plus the aggregate summary and file-skipping/error-handling behaviour. The module
previously had no tests."""

import ast
import tempfile
from pathlib import Path

from framework.analyzers.ast_analyzer import (
    ASTAnalyzer,
    ControlFlow,
    DataFlow,
    FunctionComplexity,
)


def _write(tmp_path, name, source):
    """Write ``source`` to ``tmp_path/name`` and return the file path."""
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _analyze(tmp_path, source, name="mod.py"):
    """Write a single module to a clean directory and return its full analysis.

    The analyzer skips any path containing 'test' (to ignore test files), and
    pytest's ``tmp_path`` lives under ``.../test_.../`` — so we write to a fresh
    temp dir whose path has no 'test', or every file would be skipped.
    """
    d = Path(tempfile.mkdtemp(prefix="astmod_"))
    (d / name).write_text(source, encoding="utf-8")
    return ASTAnalyzer(d).analyze_python()


def _func(result, name):
    """Pull the function-metrics dict for ``name`` out of an analysis result."""
    return next(f for f in result["functions"] if f["name"] == name)


# ---- dataclasses ----


def test_function_complexity_source_file_defaults_to_none():
    fc = FunctionComplexity(
        name="f",
        cyclomatic_complexity=1,
        cognitive_complexity=0,
        lines_of_code=1,
        num_parameters=0,
        num_returns=0,
        num_branches=0,
        num_loops=0,
        nested_depth=0,
    )
    assert fc.source_file is None


def test_data_flow_defaults_to_empty_collections():
    df = DataFlow(variable="x", source="input")
    assert df.transformations == []
    assert df.sinks == []
    assert df.source_file is None


def test_control_flow_defaults_to_empty_collections():
    cf = ControlFlow(node_type="if")
    assert cf.condition is None
    assert cf.branches == []
    assert cf.children == []
    assert cf.parent is None


# ---- discovery / summary ----


def test_empty_directory_yields_zero_functions_and_zero_average():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path

        result = ASTAnalyzer(Path(d)).analyze_python()
    assert result["functions"] == []
    assert result["summary"]["total_functions"] == 0
    assert result["summary"]["average_complexity"] == 0


def test_simple_function_is_discovered_with_base_complexity(tmp_path):
    result = _analyze(tmp_path, "def greet():\n    return 1\n")
    assert result["summary"]["total_functions"] == 1
    fn = _func(result, "greet")
    assert fn["cyclomatic_complexity"] == 1
    assert fn["num_returns"] == 1


def test_async_function_is_discovered(tmp_path):
    result = _analyze(tmp_path, "async def fetch():\n    return 2\n")
    assert _func(result, "fetch")["name"] == "fetch"


def test_multiple_functions_counted_in_summary(tmp_path):
    source = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
    result = _analyze(tmp_path, source)
    assert result["summary"]["total_functions"] == 2


def test_average_complexity_is_mean_across_functions(tmp_path):
    # a: complexity 1, b: complexity 2 (one if) -> average 1.5
    source = "def a():\n    return 1\n\n\ndef b(x):\n    if x:\n        return 2\n    return 3\n"
    result = _analyze(tmp_path, source)
    assert result["summary"]["average_complexity"] == 1.5


# ---- file skipping ----


def test_files_with_test_in_path_are_skipped(tmp_path):
    _write(tmp_path, "test_thing.py", "def helper():\n    return 1\n")
    result = ASTAnalyzer(tmp_path).analyze_python()
    assert result["functions"] == []


def test_pycache_files_are_skipped(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    _write(cache, "mod.py", "def cached():\n    return 1\n")
    result = ASTAnalyzer(tmp_path).analyze_python()
    assert result["functions"] == []


def test_non_python_files_are_ignored(tmp_path):
    _write(tmp_path, "notes.txt", "def not_python(): pass")
    result = ASTAnalyzer(tmp_path).analyze_python()
    assert result["functions"] == []


# ---- error handling ----


def test_if_statement_increments_cyclomatic_complexity(tmp_path):
    source = "def f(x):\n    if x:\n        return 1\n    return 0\n"
    assert _func(_analyze(tmp_path, source), "f")["cyclomatic_complexity"] == 2


def test_loops_increment_cyclomatic_complexity(tmp_path):
    source = "def f(items):\n    for i in items:\n        while i:\n            i -= 1\n"
    # base 1 + for + while = 3
    assert _func(_analyze(tmp_path, source), "f")["cyclomatic_complexity"] == 3


def test_boolean_operator_adds_one_per_extra_operand(tmp_path):
    source = "def f(a, b, c):\n    return a and b and c\n"
    # base 1 + (3 values - 1) = 3
    assert _func(_analyze(tmp_path, source), "f")["cyclomatic_complexity"] == 3


def test_except_handler_increments_cyclomatic_complexity(tmp_path):
    source = "def f():\n    try:\n        return 1\n    except ValueError:\n        return 0\n"
    assert _func(_analyze(tmp_path, source), "f")["cyclomatic_complexity"] == 2


# ---- counts ----


def test_parameter_count_matches_signature(tmp_path):
    source = "def f(a, b, c):\n    return a\n"
    assert _func(_analyze(tmp_path, source), "f")["num_parameters"] == 3


def test_return_count_matches_return_statements(tmp_path):
    source = "def f(x):\n    if x:\n        return 1\n    return 2\n"
    assert _func(_analyze(tmp_path, source), "f")["num_returns"] == 2


def test_branch_count_includes_if_and_ifexp(tmp_path):
    source = "def f(x):\n    y = 1 if x else 0\n    if y:\n        return y\n"
    # one IfExp + one If = 2 branches
    assert _func(_analyze(tmp_path, source), "f")["num_branches"] == 2


def test_loop_count_includes_for_and_while(tmp_path):
    source = "def f(items):\n    for i in items:\n        pass\n    while False:\n        pass\n"
    assert _func(_analyze(tmp_path, source), "f")["num_loops"] == 2


def test_lines_of_code_spans_function_definition(tmp_path):
    source = "def f():\n    a = 1\n    b = 2\n    return a + b\n"
    assert _func(_analyze(tmp_path, source), "f")["lines_of_code"] == 4


# ---- cognitive complexity & nesting ----


def test_flat_function_has_zero_cognitive_complexity(tmp_path):
    source = "def f():\n    return 1\n"
    assert _func(_analyze(tmp_path, source), "f")["cognitive_complexity"] == 0


def test_nested_control_increases_cognitive_complexity(tmp_path):
    source = "def f(x):\n    if x:\n        for i in x:\n            if i:\n                return i\n"
    fn = _func(_analyze(tmp_path, source), "f")
    assert fn["cognitive_complexity"] > 0


def test_nested_depth_reflects_deepest_nesting(tmp_path):
    source = "def f(x):\n" "    if x:\n" "        for i in x:\n" "            while i:\n" "                i -= 1\n"
    # if -> for -> while = depth 3
    assert _func(_analyze(tmp_path, source), "f")["nested_depth"] == 3


def test_with_statement_contributes_to_nested_depth(tmp_path):
    source = "def f():\n    with open('x') as fh:\n        return fh\n"
    assert _func(_analyze(tmp_path, source), "f")["nested_depth"] == 1


def test_high_complexity_functions_are_flagged_in_summary(tmp_path):
    # Build a function with many if-branches to exceed the >10 threshold.
    body = "\n".join(f"    if x == {i}:\n        return {i}" for i in range(12))
    source = f"def big(x):\n{body}\n"
    result = _analyze(tmp_path, source)
    assert result["summary"]["high_complexity_functions"] == 1


# ---- source_file plumbing ----


def test_source_file_is_recorded_on_each_function(tmp_path):
    result = _analyze(tmp_path, "def f():\n    return 1\n", name="mymod.py")
    assert _func(result, "f")["source_file"].endswith("mymod.py")


# ---- private conversion helpers ----


def test_dataflow_to_dict_round_trips_fields(tmp_path):
    analyzer = ASTAnalyzer(tmp_path)
    df = DataFlow(variable="x", source="in", transformations=["t"], sinks=["s"], source_file="f.py")
    d = analyzer._dataflow_to_dict(df)
    assert d == {
        "variable": "x",
        "source": "in",
        "transformations": ["t"],
        "sinks": ["s"],
        "source_file": "f.py",
    }


def test_controlflow_to_dict_round_trips_fields(tmp_path):
    analyzer = ASTAnalyzer(tmp_path)
    cf = ControlFlow(node_type="if", condition="x > 0", branches=["a"], parent="p", children=["c"])
    d = analyzer._controlflow_to_dict(cf)
    assert d == {
        "node_type": "if",
        "condition": "x > 0",
        "branches": ["a"],
        "parent": "p",
        "children": ["c"],
    }


def test_lines_of_code_is_zero_when_position_info_missing(tmp_path):
    # Build a FunctionDef node by hand without lineno/end_lineno to exercise
    # the fallback branch in _analyze_function.
    analyzer = ASTAnalyzer(tmp_path)
    node = ast.parse("def f():\n    return 1\n").body[0]
    del node.lineno
    del node.end_lineno
    analyzer._analyze_function(node, tmp_path / "x.py")
    assert analyzer.functions[0].lines_of_code == 0
