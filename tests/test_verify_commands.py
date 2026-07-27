"""Behavior tests for the `verify` CLI group (multi-language test verification).

Runs the real MultiLanguageVerifier over tmp files: a clean Python test, a
directory scan with a report export, the single-file path, the unsupported-type
error path, the static `languages` listing, and `lint` with/without --fix.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.verify_commands import verify


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _py_test(tmp_path: Path, name: str = "test_login.py") -> Path:
    path = tmp_path / name
    path.write_text(
        "import pytest\n\n\ndef test_login():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    return path


def test_languages_lists_supported(runner):
    result = runner.invoke(verify, ["languages"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Python" in result.output
    assert "Kotlin" in result.output


def test_file_verifies_python(runner, tmp_path):
    result = runner.invoke(verify, ["file", str(_py_test(tmp_path))])
    _no_crash(result)
    # Clean file passes; command renders the verification panel.
    assert "Verification Result" in result.output


def test_file_unsupported_type_exits_one(runner, tmp_path):
    weird = tmp_path / "notes.xyz"
    weird.write_text("nothing to see", encoding="utf-8")
    result = runner.invoke(verify, ["file", str(weird)])
    _no_crash(result)
    assert result.exit_code == 1
    assert "Unsupported" in result.output


def test_check_directory_and_summary(runner, tmp_path):
    _py_test(tmp_path)
    result = runner.invoke(verify, ["check", str(tmp_path)])
    _no_crash(result)
    assert "Verification Summary" in result.output
    assert "Total Files" in result.output


def test_check_writes_report(runner, tmp_path):
    _py_test(tmp_path)
    report = tmp_path / "report.json"
    result = runner.invoke(verify, ["check", str(tmp_path), "--output", str(report)])
    _no_crash(result)
    assert report.exists()


def test_check_empty_dir_reports_no_files(runner, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(verify, ["check", str(empty)])
    _no_crash(result)
    assert "No supported files found" in result.output


def test_lint_without_fix(runner, tmp_path):
    _py_test(tmp_path)
    result = runner.invoke(verify, ["lint", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    # Without --fix the command only reports fixable-issue counts.
    assert "auto-fix" in result.output.lower()


def test_lint_with_fix(runner, tmp_path):
    _py_test(tmp_path)
    result = runner.invoke(verify, ["lint", str(tmp_path), "--fix"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Fixed" in result.output
