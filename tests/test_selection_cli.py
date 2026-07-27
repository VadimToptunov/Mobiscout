"""Behaviour tests for `mobiscout select` (auto/by-files/estimate).

These exercise the real ``TestSelector`` mapping of changed source files to
affected tests over a temporary project tree (naming-convention + import
analysis run for real). Git history is not mocked: ``select auto`` runs the real
``ChangeAnalyzer`` against a non-repo working dir, which deterministically yields
"no changes" — guarding that the empty-change path stays graceful.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.selection_commands import select


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _scaffold():
    """Inside an isolated cwd, create a source file with a matching test file."""
    Path("tests").mkdir()
    Path("tests/test_foo.py").write_text(
        "def test_alpha():\n    assert True\n\n\ndef test_beta():\n    assert True\n",
        encoding="utf-8",
    )
    Path("foo.py").write_text("def foo():\n    return 1\n", encoding="utf-8")


# --------------------------------------------------------------------------- by-files


def test_by_files_selects_matching_tests(runner):
    with runner.isolated_filesystem():
        _scaffold()
        result = runner.invoke(select, ["by-files", "--files", "foo.py"])
        _no_crash(result)
        assert result.exit_code == 0
        # test_foo.py matches foo.py by naming convention → its tests are selected.
        assert "Selected" in result.output
        assert "test_alpha" in result.output or "test_beta" in result.output


def test_by_files_no_match(runner):
    with runner.isolated_filesystem():
        _scaffold()
        result = runner.invoke(select, ["by-files", "--files", "wholly_unrelated_xyz.py"])
        _no_crash(result)
        assert result.exit_code == 0
        assert "No tests affected" in result.output


# --------------------------------------------------------------------------- estimate


def test_estimate_with_changed_files(runner):
    with runner.isolated_filesystem():
        _scaffold()
        result = runner.invoke(select, ["estimate", "--changed-files", "foo.py"])
        _no_crash(result)
        assert result.exit_code == 0
        assert "Estimated Execution Time" in result.output


def test_estimate_without_changed_files(runner):
    with runner.isolated_filesystem():
        _scaffold()
        result = runner.invoke(select, ["estimate"])
        _no_crash(result)
        assert result.exit_code == 0
        # No changed files → empty selection → zero-second estimate.
        assert "0 seconds" in result.output


# ------------------------------------------------------------------------------- auto


def test_auto_no_changes_is_graceful(runner):
    with runner.isolated_filesystem():
        _scaffold()
        result = runner.invoke(select, ["auto"])
        _no_crash(result)
        # Not a git repo → analyzer finds no changes → clean early return.
        assert result.exit_code == 0
        assert "No changes detected" in result.output


def test_auto_selects_and_saves_when_changes(runner, monkeypatch):
    # Stub only the git boundary (ChangeAnalyzer) so the rest of `auto` — real
    # test selection, table render, and output-file writing — runs end-to-end.
    import framework.cli.selection_commands as sel_mod
    from framework.selection.change_analyzer import FileChange, ChangeType

    class _FakeAnalyzer:
        def __init__(self, repo_path):
            pass

        def get_changes(self, base, target):
            return [FileChange(path=Path("foo.py"), change_type=ChangeType.MODIFIED)]

    monkeypatch.setattr(sel_mod, "ChangeAnalyzer", _FakeAnalyzer)

    with runner.isolated_filesystem():
        _scaffold()
        result = runner.invoke(select, ["auto", "--output", "selected.txt"])
        _no_crash(result)
        assert result.exit_code == 0
        assert "Selected" in result.output
        saved = Path("selected.txt").read_text()
        assert "test_foo.py::" in saved


def test_auto_handles_analyzer_error(runner, monkeypatch):
    import framework.cli.selection_commands as sel_mod

    class _BoomAnalyzer:
        def __init__(self, repo_path):
            pass

        def get_changes(self, base, target):
            raise RuntimeError("git exploded")

    monkeypatch.setattr(sel_mod, "ChangeAnalyzer", _BoomAnalyzer)
    with runner.isolated_filesystem():
        _scaffold()
        result = runner.invoke(select, ["auto"])
        # The command catches and reports failure via click.Abort (non-zero exit).
        assert result.exit_code != 0
        assert "Test selection failed" in result.output
