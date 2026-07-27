"""Behaviour tests for the advanced security subcommands that were otherwise
uncovered (`pinning`, `binary`, `rootcheck`, `owasp`) plus the clean / bad-path
branches of `secrets`, `code`, `privacy`.

Everything runs the real analyzers over tmp source trees (regex-based scanning,
no external tooling) — except `binary`, whose APK analysis shells out to apktool.
That single external boundary is stubbed with real ``SecurityVulnerability``
objects so the CLI's table build + severity→exit-code logic is exercised for real.
"""

import importlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.security import security
from framework.security.advanced_security import (
    RiskLevel,
    SecurityVulnerability,
)
from framework.security.advanced.base import OWASPMobileTop10


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _project(tmp_path: Path, files):
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return str(tmp_path)


def _vuln(risk, title="Debuggable", vid="BIN-X"):
    return SecurityVulnerability(
        id=vid,
        title=title,
        description="desc",
        owasp_category=OWASPMobileTop10.M7_INSUFFICIENT_BINARY_PROTECTION,
        risk_level=risk,
        cvss_score=7.5,
        cwe_ids=[489],
        location="AndroidManifest.xml",
        evidence="ev",
        remediation="Fix it in release builds by disabling the flag entirely please.",
    )


# --------------------------------------------------------------------------- pinning


def test_pinning_missing_path_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["pinning", str(tmp_path / "nope"), "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 1


def test_pinning_missing_reports_gap_and_exits_one(runner, tmp_path):
    src = _project(tmp_path, {"App.kt": "class App {}\n"})
    result = runner.invoke(security, ["pinning", src, "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "No Certificate Pinning" in result.output


def test_pinning_present_is_clean(runner, tmp_path):
    src = _project(tmp_path, {"Net.kt": "val p = CertificatePinner.Builder()\n"})
    result = runner.invoke(security, ["pinning", src, "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "properly configured" in result.output


# --------------------------------------------------------------------------- binary


def test_binary_ios_not_supported_exits_two(runner, tmp_path):
    (tmp_path / "app.ipa").write_text("x", encoding="utf-8")
    result = runner.invoke(security, ["binary", str(tmp_path / "app.ipa"), "-p", "ios"])
    _no_crash(result)
    assert result.exit_code == 2
    assert "not supported" in result.output


def test_binary_missing_path_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["binary", str(tmp_path / "nope.apk"), "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 1


def test_binary_android_findings_table_and_exit_code(runner, tmp_path, monkeypatch):
    apk = tmp_path / "app.apk"
    apk.write_text("x", encoding="utf-8")

    adv = importlib.import_module("framework.cli.security.advanced")
    findings = [
        _vuln(RiskLevel.CRITICAL, "Critical thing", "C1"),
        _vuln(RiskLevel.HIGH, "High thing", "H1"),
        _vuln(RiskLevel.MEDIUM, "Medium thing", "M1"),
        _vuln(RiskLevel.LOW, "Low thing", "L1"),
    ]

    class _FakeBin:
        def analyze_android_apk(self, path):
            return findings

    monkeypatch.setattr(adv, "BinarySecurityAnalyzer", _FakeBin)
    result = runner.invoke(security, ["binary", str(apk), "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 2  # a CRITICAL finding forces exit 2
    assert "Critical thing" in result.output and "High thing" in result.output


def test_binary_android_high_only_exits_one(runner, tmp_path, monkeypatch):
    apk = tmp_path / "app.apk"
    apk.write_text("x", encoding="utf-8")
    adv = importlib.import_module("framework.cli.security.advanced")

    class _FakeBin:
        def analyze_android_apk(self, path):
            return [_vuln(RiskLevel.HIGH, "High thing", "H1")]

    monkeypatch.setattr(adv, "BinarySecurityAnalyzer", _FakeBin)
    result = runner.invoke(security, ["binary", str(apk), "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 1


def test_binary_android_no_findings_exits_zero(runner, tmp_path, monkeypatch):
    apk = tmp_path / "app.apk"
    apk.write_text("x", encoding="utf-8")
    adv = importlib.import_module("framework.cli.security.advanced")

    class _FakeBin:
        def analyze_android_apk(self, path):
            return []

    monkeypatch.setattr(adv, "BinarySecurityAnalyzer", _FakeBin)
    result = runner.invoke(security, ["binary", str(apk), "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "checks passed" in result.output


# ------------------------------------------------------------------------- rootcheck


def test_rootcheck_missing_path_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["rootcheck", str(tmp_path / "nope"), "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 1


def test_rootcheck_reports_gap(runner, tmp_path):
    src = _project(tmp_path, {"App.kt": "class App {}\n"})
    result = runner.invoke(security, ["rootcheck", src, "-p", "android"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "detection gap" in result.output


# ------------------------------------------------------------------------------ owasp


def test_owasp_lists_top10(runner):
    result = runner.invoke(security, ["owasp"])
    _no_crash(result)
    assert "OWASP Mobile Top 10" in result.output
    assert "M10" in result.output


# ------------------------------------------------- clean / bad-path branches of others


def test_secrets_missing_path_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["secrets", str(tmp_path / "nope")])
    _no_crash(result)
    assert result.exit_code == 1
    assert "Path not found" in result.output


def test_secrets_clean_tree_exits_zero(runner, tmp_path):
    src = _project(tmp_path, {"clean.py": "greeting = 'hello world'\n"})
    result = runner.invoke(security, ["secrets", src])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No hardcoded secrets" in result.output


def test_code_missing_path_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["code", str(tmp_path / "nope")])
    _no_crash(result)
    assert result.exit_code == 1


def test_code_clean_tree_exits_zero(runner, tmp_path):
    src = _project(tmp_path, {"clean.py": "value = 2 + 2\n"})
    result = runner.invoke(security, ["code", src, "-l", "python"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No secure coding issues" in result.output


def test_code_findings_grouped_and_report_written(runner, tmp_path):
    # Weak RNG + string-built SQL are real secure-coding findings; the command
    # groups them by OWASP category, writes a JSON report, and exits non-zero.
    src = _project(
        tmp_path,
        {"A.java": 'int x = Math.random();\nString q = rawQuery("S" + id);\n'},
    )
    out = tmp_path / "code.json"
    result = runner.invoke(security, ["code", src, "-l", "all", "-o", str(out)])
    _no_crash(result)
    assert result.exit_code in (1, 2)  # findings present
    assert "issue(s)" in result.output
    assert out.exists()
    import json

    assert len(json.loads(out.read_text(encoding="utf-8"))) >= 1


def test_privacy_clean_tree_exits_zero(runner, tmp_path):
    src = _project(tmp_path, {"clean.py": "total = 1\n"})
    result = runner.invoke(security, ["privacy", src, "-r", "gdpr"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No" in result.output and "compliance issues" in result.output


def test_privacy_writes_report_when_findings(runner, tmp_path):
    # Logging an email address is a real detected PII-logging privacy issue.
    src = _project(tmp_path, {"log.py": 'print("contact: user@example.com")\n'})
    out = tmp_path / "privacy.json"
    result = runner.invoke(security, ["privacy", src, "-r", "all", "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 1  # a PII-logging finding was produced
    assert out.exists()
    import json

    assert isinstance(json.loads(out.read_text(encoding="utf-8")), list)
