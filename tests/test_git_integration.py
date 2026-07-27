"""Tests for framework.healing.git_integration.

These drive the real git operations the healer performs against a genuine
temporary repository (git init in tmp_path): staging and committing healed
Page Object files, creating a branch for the heal, producing a diff report,
reverting a heal commit, listing Auto-heal history, reporting a clean/dirty
tree, and persisting healing metadata JSON. Only the repository is local; no
remote/push is involved. Commit hashes and history are read back from git, not
fabricated.
"""

import json
import subprocess
from pathlib import Path

import pytest

from framework.healing.git_integration import GitIntegration, GitCommitInfo


def _run(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A real git repo with one committed file and identity configured."""
    _run(tmp_path, "init")
    _run(tmp_path, "config", "user.email", "healer@test.local")
    _run(tmp_path, "config", "user.name", "Healer")
    _run(tmp_path, "config", "commit.gpgsign", "false")
    seed = tmp_path / "README.md"
    seed.write_text("seed\n")
    _run(tmp_path, "add", "README.md")
    _run(tmp_path, "commit", "-m", "initial")
    return tmp_path


def _details(file_path: Path):
    return [
        {
            "element_name": "login_button",
            "file_path": str(file_path),
            "old_selector": ("id", "old_login"),
            "new_selector": ("accessibility_id", "login"),
            "confidence": 0.91,
            "strategy": "accessibility_id",
        }
    ]


def _head_message(repo) -> str:
    out = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=repo, capture_output=True, text=True, check=True)
    return out.stdout


def test_commit_healing_creates_real_commit(repo):
    page = repo / "login_page.py"
    page.write_text('login_button = ("accessibility_id", "login")\n')

    info = GitIntegration(repo).commit_healing([page], _details(page))

    assert isinstance(info, GitCommitInfo)
    # hash is real: git can resolve it and it is HEAD
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert info.commit_hash == head
    assert info.selectors_healed == 1
    assert info.files_changed == [page]
    # commit message carries the healing detail
    msg = _head_message(repo)
    assert "Auto-heal: Fixed broken selectors" in msg
    assert "login_button" in msg
    assert "Confidence: 0.91" in msg
    assert "accessibility_id" in msg
    # the file is actually committed (working tree clean afterwards)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert status.strip() == ""


def test_commit_healing_on_new_branch(repo):
    page = repo / "cart_page.py"
    page.write_text('add = ("id", "cart_add")\n')

    info = GitIntegration(repo).commit_healing([page], _details(page), branch_name="heal/cart")

    assert info is not None
    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert current == "heal/cart"


def test_commit_healing_reuses_existing_branch(repo):
    _run(repo, "branch", "heal/reuse")
    page = repo / "p.py"
    page.write_text("x = 1\n")
    info = GitIntegration(repo).commit_healing([page], _details(page), branch_name="heal/reuse")
    assert info is not None
    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert current == "heal/reuse"


def test_commit_healing_file_outside_repo_returns_none(tmp_path, repo):
    """_git_add's relative_to raises ValueError for a path outside the repo;
    commit_healing catches it and returns None instead of raising."""
    outside = tmp_path.parent / "outside.py"
    outside.write_text("x = 1\n")
    try:
        info = GitIntegration(repo).commit_healing([outside], _details(outside))
        assert info is None
    finally:
        if outside.exists():
            outside.unlink()


def test_commit_healing_nothing_to_commit_returns_none(repo):
    """Committing an already-committed (unchanged) file fails the git commit and
    returns None rather than a bogus GitCommitInfo."""
    git = GitIntegration(repo)
    page = repo / "already.py"
    page.write_text("v = 1\n")
    first = git.commit_healing([page], _details(page))
    assert first is not None
    # second call: file unchanged, nothing staged -> git commit fails
    assert git.commit_healing([page], _details(page)) is None


def test_create_diff_report_shows_uncommitted_change(repo):
    seed = repo / "README.md"
    seed.write_text("seed\nnew line\n")

    report = GitIntegration(repo).create_diff_report([seed])

    assert "File: README.md" in report
    assert "+new line" in report


def test_create_diff_report_no_changes(repo):
    report = GitIntegration(repo).create_diff_report([repo / "README.md"])
    assert report == "No changes detected"


def test_revert_commit_undoes_change(repo):
    git = GitIntegration(repo)
    page = repo / "feature.py"
    page.write_text('el = ("id", "new")\n')
    info = git.commit_healing([page], _details(page))
    assert info is not None and page.exists()

    assert git.revert_commit(info.commit_hash) is True
    # the revert commit removed the added file from the tree
    assert not page.exists()


def test_revert_commit_bad_hash_returns_false(repo):
    assert GitIntegration(repo).revert_commit("deadbeefdeadbeef") is False


def test_get_healing_history_lists_autoheal_commits(repo):
    git = GitIntegration(repo)
    p1 = repo / "a.py"
    p1.write_text("a = 1\n")
    git.commit_healing([p1], _details(p1))
    p2 = repo / "b.py"
    p2.write_text("b = 2\n")
    git.commit_healing([p2], _details(p2))

    history = git.get_healing_history(limit=10)

    assert len(history) == 2
    assert all(isinstance(c, GitCommitInfo) for c in history)
    # newest first; each records the file it touched
    assert history[0].message.startswith("Auto-heal")
    touched = {c.files_changed[0].name for c in history}
    assert touched == {"a.py", "b.py"}


def test_get_healing_history_ignores_non_healing_commits(repo):
    # the seed "initial" commit is not an Auto-heal commit
    assert GitIntegration(repo).get_healing_history() == []


def test_is_repo_clean_true_then_false(repo):
    git = GitIntegration(repo)
    assert git.is_repo_clean() is True
    (repo / "dirty.py").write_text("x = 1\n")
    assert git.is_repo_clean() is False


def test_is_repo_clean_false_when_not_a_repo(tmp_path):
    not_repo = tmp_path / "plain"
    not_repo.mkdir()
    assert GitIntegration(not_repo).is_repo_clean() is False


def test_save_healing_metadata_creates_and_appends(repo):
    git = GitIntegration(repo)
    page = repo / "login_page.py"

    git.save_healing_metadata(_details(page))
    meta_path = repo / ".healing_metadata.json"
    assert meta_path.exists()
    data = json.loads(meta_path.read_text())
    assert len(data) == 1
    entry = data[0]
    assert entry["element"] == "login_button"
    assert entry["file"] == str(page)
    assert entry["old_selector"] == ["id", "old_login"]  # tuple -> JSON array
    assert entry["confidence"] == 0.91
    assert entry["strategy"] == "accessibility_id"

    # a second save appends rather than overwrites
    git.save_healing_metadata(_details(page))
    data = json.loads(meta_path.read_text())
    assert len(data) == 2


def test_save_healing_metadata_custom_path_and_corrupt_recovery(repo, tmp_path):
    git = GitIntegration(repo)
    out = tmp_path / "custom_meta.json"
    out.write_text("{ this is not valid json")  # corrupt existing file

    page = repo / "p.py"
    git.save_healing_metadata(_details(page), output_path=out)

    data = json.loads(out.read_text())
    # corrupt content is discarded, new entry written cleanly
    assert len(data) == 1
    assert data[0]["element"] == "login_button"
