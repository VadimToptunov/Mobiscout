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
def runner(monkeypatch):
    # Pin the terminal width. These commands render through Rich, which wraps to the
    # detected width — on a default-80 CI terminal a long tmp path pushed "cfg.py:1"
    # onto a continuation line (or into an ellipsis), so assertions that passed on a
    # developer's wide terminal failed on Linux/Windows runners.
    monkeypatch.setenv("COLUMNS", "200")
    return CliRunner()


_BOX_CHARS = "│─╭╮╰╯┃━┏┓┗┛"


def _unwrapped(result) -> str:
    """Output with whitespace and Rich's box-drawing characters removed.

    These commands render findings inside a Rich Panel, which wraps to the detected
    terminal width and will break *inside* a long token — a CI runner's tmp path is long
    enough that "…/cfg.py:1" split across lines, and each continuation line carries the
    panel's own "│" border. So a raw substring check failed on Linux while passing on a
    developer's wider terminal, and stripping whitespace alone was not enough: the border
    character sat in the middle of the token. Dropping both asserts the same fact
    wherever the wrap happens to land.
    """
    return "".join(c for c in result.output if not c.isspace() and c not in _BOX_CHARS)


def _no_crash(result):
    """A command may exit non-zero (findings present) but must not raise."""
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _project(tmp_path: Path, files=None):
    for name, content in (files or {"app.py": "x = 1\n"}).items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return str(tmp_path)


# An insecure pattern the secure-coding analyzer really flags (CWE-330).
_INSECURE_SRC = {"app.py": "import random\nsession_token = random.Random()\n"}


def test_code_command_reports_the_planted_insecure_pattern(runner, tmp_path):
    # Was: analyzer.analyze(source_path, language) -> TypeError (analyze takes 1 arg).
    result = runner.invoke(security, ["code", _project(tmp_path, _INSECURE_SRC), "--language", "python"])
    _no_crash(result)
    assert "Found 1 issue(s)" in result.output
    assert "Insecure Random Number Generator" in result.output


def test_code_command_reports_a_clean_file_as_clean(runner, tmp_path):
    # The other half of the contrast: without it, an analyzer that returned nothing
    # for every input would still satisfy the test above's negative space.
    result = runner.invoke(security, ["code", _project(tmp_path), "--language", "python"])
    _no_crash(result)
    assert "No secure coding issues found" in result.output


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


def test_sast_command_reports_the_planted_sinks(runner, tmp_path):
    # Was: result.vulnerabilities (SASTResult has .findings), severity == "critical"
    # (Severity is not a str-enum -> always False), export_sarif(result) -> crashes.
    result = runner.invoke(security, ["sast", _project(tmp_path, _VULN_SRC), "--language", "python"])
    _no_crash(result)
    assert "Found 3 Vulnerabilities" in result.output  # os.system, eval, the hardcoded key
    assert "command_injection" in result.output and "hardcoded_key" in result.output
    assert result.exit_code == 2  # critical findings present


def test_sast_sarif_export(runner, tmp_path):
    out = tmp_path / "sast.sarif"
    result = runner.invoke(security, ["sast", _project(tmp_path, _VULN_SRC), "-o", str(out), "--format", "sarif"])
    _no_crash(result)
    assert out.exists()


# A complete user_input -> os.system flow, which is what taint tracks (_VULN_SRC's
# `user_input` is an undefined name, so it has no source to trace from).
_TAINT_SRC = {"app.py": "import os\ncmd = input('run: ')\nos.system(cmd)\n"}


def test_taint_command_reports_the_source_to_sink_flow(runner, tmp_path):
    # Was: flow.source_line / flow.sink_line (TaintFlow has no such attrs),
    # severity.upper() on an enum -> crashes.
    result = runner.invoke(security, ["taint", _project(tmp_path, _TAINT_SRC)])
    _no_crash(result)
    assert "Found 1 taint flow issue(s)" in result.output
    assert "command_injection" in result.output
    assert "os.system" in result.output  # the sink the flow ends at
    assert result.exit_code == 1


def test_taint_command_reports_no_flow_for_a_clean_project(runner, tmp_path):
    result = runner.invoke(security, ["taint", _project(tmp_path)])
    _no_crash(result)
    assert "No taint flow vulnerabilities found" in result.output


_SECRET_SRC = {"cfg.py": "API_KEY = 'sk_live_abcdef1234567890xyz'\n"}
# PII reaching a log statement: an address the email pattern actually matches,
# through a call shape the log patterns actually recognise.
_PII_LOG_SRC = {
    "signup.py": "import logging\nlogger = logging.getLogger(__name__)\nlogger.info('new user alice@example.com')\n"
}


def test_secrets_command_reports_the_planted_key(runner, tmp_path):
    # Was: finding.file_path/line_number (only .location), finding.recommendation
    # (.remediation), risk_level.value.upper() (RiskLevel value is int) -> crashes.
    result = runner.invoke(security, ["secrets", _project(tmp_path, _SECRET_SRC)])
    _no_crash(result)
    assert "Found 1 potential secret(s)" in result.output
    assert "Hardcoded Generic API Key Detected" in result.output
    assert "cfg.py:1" in _unwrapped(result)  # reported with its file and line
    assert result.exit_code == 1


def test_privacy_command_reports_pii_reaching_a_log(runner, tmp_path):
    # Was: checker.check_compliance(...) doesn't exist (check_pii_logging /
    # check_tracking_sdks) and finding.file_path/line_number -> crashes.
    result = runner.invoke(security, ["privacy", _project(tmp_path, _PII_LOG_SRC), "-r", "gdpr"])
    _no_crash(result)
    assert "Found 1 privacy issue(s)" in result.output
    assert "PII (email) Potentially Logged" in result.output
    assert "signup.py:3" in _unwrapped(result)
    assert result.exit_code == 1


def test_privacy_command_reports_a_clean_project_as_clean(runner, tmp_path):
    result = runner.invoke(security, ["privacy", _project(tmp_path), "-r", "gdpr"])
    _no_crash(result)
    assert "No GDPR compliance issues found" in result.output
