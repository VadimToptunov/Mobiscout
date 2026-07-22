"""Coverage for change-based test selection: given a set of file changes, pick
the impacted tests (directly-changed test files, same-directory, naming
convention, and import-based dependents). Pure logic over a tmp project tree,
previously 19% covered."""

from pathlib import Path

import pytest

from framework.selection.change_analyzer import ChangeType, FileChange

# Alias the Test*-prefixed classes so pytest doesn't try to collect them as tests.
from framework.selection.test_selector import ImpactLevel
from framework.selection.test_selector import TestImpact as Impact
from framework.selection.test_selector import TestSelector as Selector


@pytest.fixture()
def project(tmp_path):
    """A tiny project: a source module and a matching test that imports it."""
    root = tmp_path
    (root / "pkg").mkdir()
    (root / "pkg" / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    tests = root / "tests"
    tests.mkdir()
    (tests / "test_calculator.py").write_text(
        "from pkg.calculator import add\n\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n\n\n"
        "class TestAdd:\n    def test_more(self):\n        assert add(2, 2) == 4\n",
        encoding="utf-8",
    )
    (tests / "test_unrelated.py").write_text("def test_nothing():\n    assert True\n", encoding="utf-8")
    return root, tests


def _change(path, change_type=ChangeType.MODIFIED):
    return FileChange(path=path, change_type=change_type, old_path=None, lines_added=1, lines_deleted=0)


def test_select_all_strategy(project):
    root, tests = project
    selector = Selector(root, tests)
    impacts = selector.select_tests([], selection_strategy="all")
    names = {i.test_name for i in impacts}
    assert "test_add" in names
    assert "TestAdd.test_more" in names  # class-based test discovered
    assert "test_nothing" in names
    assert all(i.impact_level == ImpactLevel.NONE for i in impacts)


def test_direct_test_file_change_is_high_impact(project):
    root, tests = project
    selector = Selector(root, tests)
    impacts = selector.select_tests([_change(tests / "test_calculator.py")])
    assert impacts
    assert all(i.impact_level == ImpactLevel.HIGH for i in impacts)
    assert {i.test_name for i in impacts} == {"test_add", "TestAdd.test_more"}


def test_deleted_changes_are_skipped(project):
    root, tests = project
    selector = Selector(root, tests)
    impacts = selector.select_tests([_change(tests / "test_calculator.py", ChangeType.DELETED)])
    assert impacts == []


def test_source_change_finds_dependent_tests_by_naming_and_import(project):
    root, tests = project
    selector = Selector(root, tests)
    impacts = selector.select_tests([_change(root / "pkg" / "calculator.py")], selection_strategy="smart")
    # test_calculator.py matches by name and imports the module -> impacted.
    files = {i.test_file.name for i in impacts}
    assert "test_calculator.py" in files
    reasons = " ".join(r for i in impacts for r in i.reasons).lower()
    assert "naming convention" in reasons or "imports" in reasons


def test_is_test_file(project):
    root, tests = project
    selector = Selector(root, tests)
    assert selector._is_test_file(Path("tests/test_x.py"))
    assert selector._is_test_file(Path("x_test.py"))
    assert not selector._is_test_file(Path("pkg/module.py"))


def test_get_tests_from_file_handles_bad_syntax(tmp_path):
    selector = Selector(tmp_path, tmp_path)
    broken = tmp_path / "test_broken.py"
    broken.write_text("def test_x(:\n    pass\n", encoding="utf-8")
    assert selector._get_tests_from_file(broken) == []  # syntax error -> no tests, no raise


def test_get_tests_from_file_is_cached(project):
    root, tests = project
    selector = Selector(root, tests)
    tf = tests / "test_calculator.py"
    first = selector._get_tests_from_file(tf)
    assert selector._test_cache[tf] is first  # cached by path


def test_estimate_runtime(project):
    root, tests = project
    selector = Selector(root, tests)
    impacts = [
        Impact(tests / "t.py", "test_a", ImpactLevel.HIGH, []),
        Impact(tests / "t.py", "test_b", ImpactLevel.HIGH, []),
    ]
    assert selector.estimate_runtime(impacts) == 2.0


def test_generate_report(project):
    root, tests = project
    selector = Selector(root, tests)
    assert selector.generate_report([]) == "No tests selected"
    impacts = selector.select_tests([_change(tests / "test_calculator.py")])
    report = selector.generate_report(impacts)
    assert "Selected" in report and "test_add" in report


def test_test_impact_hash_is_keyed_on_file_and_name():
    a = Impact(Path("t.py"), "test_x", ImpactLevel.HIGH, ["r1"])
    b = Impact(Path("t.py"), "test_x", ImpactLevel.MEDIUM, ["r2"])
    same = Impact(Path("t.py"), "test_x", ImpactLevel.HIGH, ["r1"])
    assert hash(a) == hash(b)  # hash keyed only on (file, name)
    assert a == same and len({a, same}) == 1  # identical impacts dedupe in a set
    assert a != b  # but dataclass equality still compares all fields
