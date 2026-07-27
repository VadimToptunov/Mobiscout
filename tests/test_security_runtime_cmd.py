"""Behavior tests for the `security runtime` / `security protections` commands.

Both drive the RuntimeProtectionAnalyzer end-to-end through CliRunner over a real
(tiny) zip-based APK. The sample app ships none of the checked protections, so the
analyzer legitimately scores it "WEAK" and the commands exit 1 — that non-zero exit
is asserted as real behavior, not merely "did not crash". Report export (json/html)
is exercised so the serialisation call sites stay wired.
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
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _apk(tmp_path: Path, name: str = "app.apk") -> str:
    apk = tmp_path / name
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("classes.dex", b"just some bytes, no protections here")
        z.writestr("AndroidManifest.xml", b"<manifest package='com.example.app'/>")
    return str(apk)


def test_runtime_weak_app_exits_one(runner, tmp_path):
    # A bare app has no protections -> WEAK verdict -> exit code 1.
    result = runner.invoke(security, ["runtime", _apk(tmp_path), "--platform", "android"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "Protection Score" in result.output


def test_runtime_writes_json_report(runner, tmp_path):
    out = tmp_path / "runtime.json"
    result = runner.invoke(
        security,
        ["runtime", _apk(tmp_path), "-p", "android", "-o", str(out), "-f", "json"],
    )
    _no_crash(result)
    # Exit is 1 (weak) but the report must still be written before exiting.
    assert out.exists()
    assert out.read_text(encoding="utf-8").strip().startswith("{")


def test_runtime_writes_html_report(runner, tmp_path):
    out = tmp_path / "runtime.html"
    result = runner.invoke(
        security,
        ["runtime", _apk(tmp_path), "-p", "android", "-o", str(out), "-f", "html"],
    )
    _no_crash(result)
    assert out.exists()


def test_runtime_missing_file_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["runtime", str(tmp_path / "nope.apk"), "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_runtime_requires_platform(runner, tmp_path):
    # --platform is required; omitting it is a usage error (exit 2), never a crash.
    result = runner.invoke(security, ["runtime", _apk(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 2


def test_protections_weak_app_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["protections", _apk(tmp_path), "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "Protection Coverage" in result.output


def test_protections_missing_file_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["protections", str(tmp_path / "ghost.apk"), "-p", "ios"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "not found" in result.output.lower()
