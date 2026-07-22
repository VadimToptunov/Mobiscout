"""Regression tests for the security CLI commands whose call sites were broken:
they invoked analyzer methods with the wrong arity / a wrong result shape and
would crash (TypeError / AttributeError) the moment the command ran. These drive
each command end-to-end through CliRunner over a tmp project so a re-break shows
up as a non-SystemExit exception.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.security import security


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    """A command may exit non-zero (findings present) but must not raise."""
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _project(tmp_path: Path, files=None):
    for name, content in (files or {"app.py": "x = 1\n"}).items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return str(tmp_path)


def test_code_command_runs(runner, tmp_path):
    # Was: analyzer.analyze(source_path, language) -> TypeError (analyze takes 1 arg).
    result = runner.invoke(security, ["code", _project(tmp_path), "--language", "python"])
    _no_crash(result)


def test_sbom_command_writes_file(runner, tmp_path):
    # Was: analyzer.generate_sbom(result, output, format=) -> wrong method/arity.
    out = tmp_path / "out.sbom"
    result = runner.invoke(
        security,
        [
            "sbom",
            _project(tmp_path, {"requirements.txt": "flask==3.0\n"}),
            "--output",
            str(out),
            "--format",
            "cyclonedx",
        ],
    )
    _no_crash(result)
    assert out.exists()


def test_supply_chain_sbom_runs(runner, tmp_path):
    # Was: analyzer.generate_sbom(result, output) -> wrong method/arity.
    out = tmp_path / "sc.sbom"
    result = runner.invoke(
        security,
        [
            "supply-chain",
            _project(tmp_path, {"requirements.txt": "flask==3.0\n"}),
            "--output",
            str(out),
            "--format",
            "sbom",
        ],
    )
    _no_crash(result)
    assert out.exists()


@pytest.mark.parametrize("fmt", ["sarif", "html", "json"])
def test_full_scan_exports_each_format(runner, tmp_path, fmt):
    # Was: full_scan(app_path, platform, app_name) -> wrong arity, AND the command
    # then read result.findings / result.to_dict() on a dict -> AttributeError.
    out = tmp_path / "reports"
    result = runner.invoke(
        security,
        ["full", _project(tmp_path), "-p", "android", "-n", "TestApp", "-o", str(out), "-f", fmt],
    )
    _no_crash(result)
    assert out.exists() and any(out.iterdir())  # a report file was written


# A source file with clear findings so the display code paths actually run.
_VULN_SRC = {"app.py": "import os\nos.system(user_input)\neval(data)\npassword = 'hardcoded12345'\n"}


def test_sast_command_runs(runner, tmp_path):
    # Was: result.vulnerabilities (SASTResult has .findings), severity == "critical"
    # (Severity is not a str-enum -> always False), export_sarif(result) -> crashes.
    result = runner.invoke(security, ["sast", _project(tmp_path, _VULN_SRC), "--language", "python"])
    _no_crash(result)


def test_sast_sarif_export(runner, tmp_path):
    out = tmp_path / "sast.sarif"
    result = runner.invoke(security, ["sast", _project(tmp_path, _VULN_SRC), "-o", str(out), "--format", "sarif"])
    _no_crash(result)
    assert out.exists()


def test_taint_command_runs(runner, tmp_path):
    # Was: flow.source_line / flow.sink_line (TaintFlow has no such attrs),
    # severity.upper() on an enum -> crashes.
    result = runner.invoke(security, ["taint", _project(tmp_path, _VULN_SRC)])
    _no_crash(result)


_SECRET_SRC = {"cfg.py": "API_KEY = 'sk_live_abcdef1234567890xyz'\nimport logging\nlogging.info(user.email)\n"}


def test_secrets_command_runs(runner, tmp_path):
    # Was: finding.file_path/line_number (only .location), finding.recommendation
    # (.remediation), risk_level.value.upper() (RiskLevel value is int) -> crashes.
    result = runner.invoke(security, ["secrets", _project(tmp_path, _SECRET_SRC)])
    _no_crash(result)


def test_privacy_command_runs(runner, tmp_path):
    # Was: checker.check_compliance(...) doesn't exist (check_pii_logging /
    # check_tracking_sdks) and finding.file_path/line_number -> crashes.
    result = runner.invoke(security, ["privacy", _project(tmp_path, _SECRET_SRC), "-r", "gdpr"])
    _no_crash(result)
