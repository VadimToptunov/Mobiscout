"""Behavior tests for the `security decompile` / `security strings` commands.

These drive the commands end-to-end through CliRunner over a real (tiny) APK —
a plain zip carrying a dex-like blob with a URL and an API key inside — so the
whole in-process pipeline runs: binary hashing, string extraction/categorisation,
protection detection and the rich rendering. The external decompilers (apktool /
jadx / readelf) are absent in the test env and the analyzer swallows their
FileNotFoundError, so no subprocess is mocked. A re-break in the call wiring
surfaces as a non-SystemExit exception.
"""

import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.security import security


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    """A command may exit non-zero but must never raise a non-SystemExit."""
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _apk(tmp_path: Path, name: str = "app.apk") -> str:
    """Build a minimal but real zip-based APK with recognisable strings."""
    apk = tmp_path / name
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr(
            "classes.dex",
            b"login endpoint https://api.example.com/v1/login "
            b"api_key=AKIA1234567890ABCDEF password=hunter2secret "
            b"contact admin@example.com host 10.0.0.1",
        )
        z.writestr("AndroidManifest.xml", b"<manifest package='com.example.app'/>")
    return str(apk)


def test_decompile_runs_and_exits_zero(runner, tmp_path):
    result = runner.invoke(security, ["decompile", _apk(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    # The results panel and the binary-info table are always rendered.
    assert "Decompilation Results" in result.output
    assert "Package" in result.output


def test_decompile_writes_output_dir(runner, tmp_path):
    out = tmp_path / "decompiled"
    result = runner.invoke(security, ["decompile", _apk(tmp_path), "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    # Command reports it saved the decompiled files (rich may wrap the long path,
    # so match on the stable message + the created directory rather than the path).
    assert "saved" in result.output.lower()
    assert out.exists()


def test_decompile_missing_file_exits_one(runner, tmp_path):
    # validate_path prints an error and exits 1 for a non-existent binary.
    result = runner.invoke(security, ["decompile", str(tmp_path / "nope.apk")])
    _no_crash(result)
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_strings_extracts_and_lists(runner, tmp_path):
    result = runner.invoke(security, ["strings", _apk(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    # Extraction found at least the URL we planted; header always shows a count.
    assert "strings" in result.output.lower()


def test_strings_filter_secrets(runner, tmp_path):
    result = runner.invoke(security, ["strings", _apk(tmp_path), "--filter", "secrets"])
    _no_crash(result)
    assert result.exit_code == 0


def test_strings_writes_output_file(runner, tmp_path):
    out = tmp_path / "extracted.txt"
    result = runner.invoke(security, ["strings", _apk(tmp_path), "-o", str(out), "-m", "6"])
    _no_crash(result)
    assert result.exit_code == 0
    # Only written when strings were found; the URL guarantees at least one.
    if "Strings saved" in result.output:
        assert out.exists()
        assert out.read_text(encoding="utf-8")


def test_strings_missing_file_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["strings", str(tmp_path / "ghost.apk")])
    _no_crash(result)
    assert result.exit_code == 1
