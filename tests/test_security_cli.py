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
