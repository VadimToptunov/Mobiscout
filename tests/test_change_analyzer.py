"""Unit tests for the git change analyzer.

Covers the FileChange/ChangeType dataclasses, the pure helpers
(get_changed_directories, filter_by_extension), and the git-backed methods.

Note: the production module invokes ``git dif`` (a typo for ``git diff``) in
get_changes/_get_file_stats/_get_staged_changes. Against a real git repo this
makes ``check=True`` raise CalledProcessError, so those paths are exercised both
against a real repo (to confirm the graceful-degradation behavior) and via a
mocked subprocess (to drive the status-line parsing branches).
"""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from framework.selection.change_analyzer import (
    ChangeAnalyzer,
    ChangeType,
    FileChange,
)


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
def _run_git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path):
    """A minimal initialized git repo with one committed file."""
    _run_git(tmp_path, "init")
    _run_git(tmp_path, "config", "user.email", "t@t.com")
    _run_git(tmp_path, "config", "user.name", "Tester")
    (tmp_path / "seed.txt").write_text("hello\n")
    _run_git(tmp_path, "add", "seed.txt")
    _run_git(tmp_path, "commit", "-m", "seed")
    return tmp_path


def _completed(stdout):
    """Build a CompletedProcess-like object with the given stdout."""
    return SimpleNamespace(stdout=stdout, stderr="", returncode=0)


# --------------------------------------------------------------------------- #
# Dataclasses / enums
# --------------------------------------------------------------------------- #
def test_change_type_values_are_lowercase_names():
    assert ChangeType.ADDED.value == "added"
    assert ChangeType.MODIFIED.value == "modified"
    assert ChangeType.DELETED.value == "deleted"
    assert ChangeType.RENAMED.value == "renamed"


def test_file_change_defaults_are_zero_and_none():
    change = FileChange(path=Path("a.py"), change_type=ChangeType.ADDED)
    assert change.old_path is None
    assert change.lines_added == 0
    assert change.lines_deleted == 0


def test_file_change_stores_provided_fields():
    change = FileChange(
        path=Path("new.py"),
        change_type=ChangeType.RENAMED,
        old_path=Path("old.py"),
        lines_added=3,
        lines_deleted=1,
    )
    assert change.old_path == Path("old.py")
    assert change.lines_added == 3
    assert change.lines_deleted == 1


# --------------------------------------------------------------------------- #
# Pure helpers: get_changed_directories
# --------------------------------------------------------------------------- #
def test_get_changed_directories_collects_parent_dirs():
    analyzer = ChangeAnalyzer(Path("/repo"))
    changes = [
        FileChange(path=Path("src/a.py"), change_type=ChangeType.MODIFIED),
        FileChange(path=Path("src/b.py"), change_type=ChangeType.ADDED),
        FileChange(path=Path("tests/c.py"), change_type=ChangeType.ADDED),
    ]
    dirs = analyzer.get_changed_directories(changes)
    assert dirs == {Path("src"), Path("tests")}


def test_get_changed_directories_excludes_deleted_files():
    analyzer = ChangeAnalyzer(Path("/repo"))
    changes = [
        FileChange(path=Path("keep/a.py"), change_type=ChangeType.MODIFIED),
        FileChange(path=Path("gone/b.py"), change_type=ChangeType.DELETED),
    ]
    dirs = analyzer.get_changed_directories(changes)
    assert dirs == {Path("keep")}


def test_get_changed_directories_empty_for_no_changes():
    analyzer = ChangeAnalyzer(Path("/repo"))
    assert analyzer.get_changed_directories([]) == set()


# --------------------------------------------------------------------------- #
# Pure helpers: filter_by_extension
# --------------------------------------------------------------------------- #
def test_filter_by_extension_keeps_only_matching_suffixes():
    analyzer = ChangeAnalyzer(Path("/repo"))
    changes = [
        FileChange(path=Path("a.py"), change_type=ChangeType.MODIFIED),
        FileChange(path=Path("b.kt"), change_type=ChangeType.ADDED),
        FileChange(path=Path("c.txt"), change_type=ChangeType.ADDED),
    ]
    filtered = analyzer.filter_by_extension(changes, [".py", ".kt"])
    assert [c.path for c in filtered] == [Path("a.py"), Path("b.kt")]


def test_filter_by_extension_returns_empty_when_none_match():
    analyzer = ChangeAnalyzer(Path("/repo"))
    changes = [FileChange(path=Path("a.md"), change_type=ChangeType.ADDED)]
    assert analyzer.filter_by_extension(changes, [".py"]) == []


# --------------------------------------------------------------------------- #
# Real-repo behavior (exercises the `git dif` typo -> graceful degradation)
# --------------------------------------------------------------------------- #
def test_get_changes_returns_empty_when_git_command_fails(git_repo, capsys):
    analyzer = ChangeAnalyzer(git_repo)
    result = analyzer.get_changes(base_branch="HEAD", target_branch="HEAD")
    assert result == []
    assert "Git command failed" in capsys.readouterr().out


def test_get_changed_files_returns_empty_list_on_failure(git_repo):
    analyzer = ChangeAnalyzer(git_repo)
    assert analyzer.get_changed_files(base_branch="HEAD", target_branch="HEAD") == []


def test_get_untracked_files_lists_new_files(git_repo):
    (git_repo / "brand_new.py").write_text("x = 1\n")
    analyzer = ChangeAnalyzer(git_repo)
    changes = analyzer._get_untracked_files()
    paths = {c.path for c in changes}
    assert Path("brand_new.py") in paths
    assert all(c.change_type is ChangeType.ADDED for c in changes)


def test_get_untracked_files_empty_when_clean(git_repo):
    analyzer = ChangeAnalyzer(git_repo)
    assert analyzer._get_untracked_files() == []


def test_get_file_stats_defaults_to_zero_on_git_failure(git_repo):
    analyzer = ChangeAnalyzer(git_repo)
    stats = analyzer._get_file_stats(Path("seed.txt"), "HEAD", "HEAD")
    assert stats == {"added": 0, "deleted": 0}


# --------------------------------------------------------------------------- #
# Parsing branches driven by a mocked subprocess
# --------------------------------------------------------------------------- #
def test_get_changes_parses_added_modified_deleted_renamed():
    analyzer = ChangeAnalyzer(Path("/repo"))
    diff_out = "M\tmod.py\nA\tadd.py\nD\tdel.py\nR100\told.py\tnew.py\n"

    def fake_run(cmd, **kwargs):
        # Name-status diff for get_changes; numstat for _get_file_stats.
        if "--numstat" in cmd:
            return _completed("5\t2\tmod.py\n")
        return _completed(diff_out)

    with patch("framework.selection.change_analyzer.subprocess.run", side_effect=fake_run):
        # target_branch != HEAD avoids the staged-changes call.
        changes = analyzer.get_changes(base_branch="main", target_branch="feature")

    by_type = {c.change_type: c for c in changes}
    assert by_type[ChangeType.MODIFIED].path == Path("mod.py")
    assert by_type[ChangeType.MODIFIED].lines_added == 5
    assert by_type[ChangeType.MODIFIED].lines_deleted == 2
    assert by_type[ChangeType.ADDED].path == Path("add.py")
    assert by_type[ChangeType.DELETED].path == Path("del.py")
    assert by_type[ChangeType.RENAMED].path == Path("new.py")
    assert by_type[ChangeType.RENAMED].old_path == Path("old.py")


def test_get_changes_skips_blank_lines():
    analyzer = ChangeAnalyzer(Path("/repo"))

    with patch(
        "framework.selection.change_analyzer.subprocess.run",
        return_value=_completed("\n\n"),
    ):
        assert analyzer.get_changes(base_branch="main", target_branch="feature") == []


def test_get_changes_appends_staged_changes_for_head_target():
    analyzer = ChangeAnalyzer(Path("/repo"))

    def fake_run(cmd, **kwargs):
        if "--cached" in cmd:
            return _completed("A\tstaged.py\n")
        return _completed("")  # empty base diff

    with patch("framework.selection.change_analyzer.subprocess.run", side_effect=fake_run):
        changes = analyzer.get_changes(base_branch="main", target_branch="HEAD")

    assert [c.path for c in changes] == [Path("staged.py")]
    assert changes[0].change_type is ChangeType.ADDED


def test_get_changes_appends_untracked_when_requested():
    analyzer = ChangeAnalyzer(Path("/repo"))

    def fake_run(cmd, **kwargs):
        if "ls-files" in cmd:
            return _completed("untracked.py\n")
        if "--cached" in cmd:
            return _completed("")
        return _completed("")

    with patch("framework.selection.change_analyzer.subprocess.run", side_effect=fake_run):
        changes = analyzer.get_changes(base_branch="main", target_branch="HEAD", include_untracked=True)

    assert Path("untracked.py") in {c.path for c in changes}


def test_get_staged_changes_parses_all_statuses():
    analyzer = ChangeAnalyzer(Path("/repo"))
    with patch(
        "framework.selection.change_analyzer.subprocess.run",
        return_value=_completed("M\tm.py\nA\ta.py\nD\td.py\n"),
    ):
        changes = analyzer._get_staged_changes()

    result = {c.path: c.change_type for c in changes}
    assert result == {
        Path("m.py"): ChangeType.MODIFIED,
        Path("a.py"): ChangeType.ADDED,
        Path("d.py"): ChangeType.DELETED,
    }


def test_get_staged_changes_returns_empty_on_error():
    analyzer = ChangeAnalyzer(Path("/repo"))
    with patch(
        "framework.selection.change_analyzer.subprocess.run",
        side_effect=subprocess.SubprocessError("boom"),
    ):
        assert analyzer._get_staged_changes() == []


def test_get_untracked_files_returns_empty_on_error():
    analyzer = ChangeAnalyzer(Path("/repo"))
    with patch(
        "framework.selection.change_analyzer.subprocess.run",
        side_effect=OSError("no git"),
    ):
        assert analyzer._get_untracked_files() == []


def test_get_file_stats_parses_numstat_counts():
    analyzer = ChangeAnalyzer(Path("/repo"))
    with patch(
        "framework.selection.change_analyzer.subprocess.run",
        return_value=_completed("10\t4\tfile.py\n"),
    ):
        stats = analyzer._get_file_stats(Path("file.py"), "main", "HEAD")
    assert stats == {"added": 10, "deleted": 4}


def test_get_file_stats_treats_binary_dash_as_zero():
    analyzer = ChangeAnalyzer(Path("/repo"))
    with patch(
        "framework.selection.change_analyzer.subprocess.run",
        return_value=_completed("-\t-\timage.png\n"),
    ):
        stats = analyzer._get_file_stats(Path("image.png"), "main", "HEAD")
    assert stats == {"added": 0, "deleted": 0}


def test_get_file_stats_returns_zero_for_empty_output():
    analyzer = ChangeAnalyzer(Path("/repo"))
    with patch(
        "framework.selection.change_analyzer.subprocess.run",
        return_value=_completed("   "),
    ):
        stats = analyzer._get_file_stats(Path("file.py"), "main", "HEAD")
    assert stats == {"added": 0, "deleted": 0}


def test_get_changed_files_uses_since_commit_as_base():
    analyzer = ChangeAnalyzer(Path("/repo"))
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed("")

    with patch("framework.selection.change_analyzer.subprocess.run", side_effect=fake_run):
        analyzer.get_changed_files(base_branch="main", target_branch="feature", since_commit="abc123")

    # since_commit overrides base_branch in the diff range.
    assert any("abc123...feature" in part for part in captured["cmd"])


def test_get_changed_files_returns_paths_from_changes():
    analyzer = ChangeAnalyzer(Path("/repo"))
    with patch(
        "framework.selection.change_analyzer.subprocess.run",
        return_value=_completed("A\tone.py\nA\ttwo.py\n"),
    ):
        paths = analyzer.get_changed_files(base_branch="main", target_branch="feature")
    assert paths == [Path("one.py"), Path("two.py")]
