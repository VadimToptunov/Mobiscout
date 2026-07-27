"""Tests for framework.healing.file_updater.

These guard the on-disk rewriting of Page Object selectors during self-healing:
the healed selector must actually replace the old one in the file, a backup with
the original bytes must be written when requested, selector values containing
regex-special characters (backslashes from UiAutomator/XPath) must be inserted
literally, and error paths (missing file, unknown language, pattern absent) must
report failure instead of corrupting the file.
"""

from pathlib import Path

from framework.healing.file_updater import FileUpdater, UpdateResult


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_update_python_selector_rewrites_file_and_backs_up(tmp_path):
    """Happy path: the .py selector line is replaced with the healed selector,
    an auto-heal comment and fallback are inserted, and a backup holding the
    original content is created."""
    po = _write(
        tmp_path / "login_page.py",
        "class LoginPage:\n" '    login_button = ("id", "login_btn")\n',
    )
    original = po.read_text(encoding="utf-8")

    result = FileUpdater(create_backup=True).update_selector(
        po, "login_button", ("id", "login_btn"), ("accessibility_id", "login"), 0.93
    )

    assert result.success is True
    new_content = po.read_text(encoding="utf-8")
    assert 'login_button = ("accessibility_id", "login")' in new_content
    assert "# Auto-healed:" in new_content
    assert "# Fallback: ('id', 'login_btn')" in new_content
    assert "confidence: 0.93" in new_content
    # backup exists and preserves the pre-heal file verbatim
    assert result.backup_path is not None and result.backup_path.exists()
    assert result.backup_path.read_text(encoding="utf-8") == original


def test_update_python_no_backup_when_disabled(tmp_path):
    po = _write(tmp_path / "p.py", '    field = ("id", "old")\n')
    result = FileUpdater(create_backup=False).update_selector(po, "field", ("id", "old"), ("xpath", "//new"), 0.5)
    assert result.success is True
    assert result.backup_path is None
    # no stray .bak files left behind
    assert not list(tmp_path.glob("*.bak.*"))


def test_selector_value_with_backslash_inserted_literally(tmp_path):
    """A new selector value containing a backslash + digit (which re.sub would
    otherwise treat as a \\1 group reference) must land in the file verbatim."""
    po = _write(tmp_path / "p.py", '    el = ("id", "old")\n')
    tricky = 'new UiSelector().text("A\\1B")'
    result = FileUpdater(create_backup=False).update_selector(po, "el", ("id", "old"), ("uiautomator", tricky), 0.8)
    assert result.success is True
    assert tricky in po.read_text(encoding="utf-8")


def test_missing_file_reports_failure(tmp_path):
    result = FileUpdater().update_selector(tmp_path / "nope.py", "x", ("id", "a"), ("id", "b"), 0.1)
    assert result.success is False
    assert result.error_message == "File not found"


def test_unsupported_extension_reports_failure(tmp_path):
    po = _write(tmp_path / "p.txt", "whatever")
    result = FileUpdater().update_selector(po, "x", ("id", "a"), ("id", "b"), 0.1)
    assert result.success is False
    assert "Unsupported file type" in result.error_message


def test_pattern_not_found_reports_failure_and_leaves_file(tmp_path):
    po = _write(tmp_path / "p.py", "class X:\n    pass\n")
    before = po.read_text(encoding="utf-8")
    result = FileUpdater(create_backup=False).update_selector(po, "ghost", ("id", "missing"), ("id", "new"), 0.9)
    assert result.success is False
    assert "Selector pattern not found" in result.error_message
    assert po.read_text(encoding="utf-8") == before


def test_update_kotlin_selector(tmp_path):
    po = _write(tmp_path / "LoginPage.kt", '    val loginButton = By.id("login_btn")\n')
    result = FileUpdater(create_backup=False).update_selector(
        po, "loginButton", ("id", "login_btn"), ("accessibility_id", "login"), 0.77
    )
    assert result.success is True
    content = po.read_text(encoding="utf-8")
    assert 'val loginButton = MobileBy.AccessibilityId("login")' in content
    assert "// Auto-healed:" in content


def test_update_swift_selector(tmp_path):
    po = _write(
        tmp_path / "LoginPage.swift",
        '    var loginButton: XCUIElement { app.buttons["login_btn"] }\n',
    )
    result = FileUpdater(create_backup=False).update_selector(
        po, "loginButton", ("accessibility_id", "login_btn"), ("accessibility_id", "login"), 0.6
    )
    assert result.success is True
    content = po.read_text(encoding="utf-8")
    assert 'matching(identifier: "login")' in content
    assert "// Auto-healed:" in content


def test_restore_backup_round_trips(tmp_path):
    po = _write(tmp_path / "p.py", '    el = ("id", "old")\n')
    original = po.read_text(encoding="utf-8")
    updater = FileUpdater(create_backup=True)
    result = updater.update_selector(po, "el", ("id", "old"), ("id", "new"), 0.9)
    assert result.success and po.read_text(encoding="utf-8") != original

    assert updater.restore_backup(result.backup_path) is True
    assert po.read_text(encoding="utf-8") == original
    # backup consumed on successful restore
    assert not result.backup_path.exists()


def test_restore_backup_rejects_non_backup_path(tmp_path):
    plain = _write(tmp_path / "not_a_backup.py", "data")
    assert FileUpdater().restore_backup(plain) is False


def test_restore_backup_missing_file_returns_false(tmp_path):
    assert FileUpdater().restore_backup(tmp_path / "gone.py.bak.123") is False


def test_batch_update_returns_result_per_entry(tmp_path):
    good = _write(tmp_path / "a.py", '    el = ("id", "old")\n')
    updates = [
        (good, "el", ("id", "old"), ("id", "new"), 0.9),
        (tmp_path / "missing.py", "el", ("id", "old"), ("id", "new"), 0.9),
    ]
    results = FileUpdater(create_backup=False).batch_update(updates)
    assert len(results) == 2
    assert isinstance(results[0], UpdateResult)
    assert results[0].success is True
    assert results[1].success is False
