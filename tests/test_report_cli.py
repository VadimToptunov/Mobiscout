"""Behaviour tests for `mobiscout report` (generate/summary/list).

Runs the real ``ReportGenerator`` end-to-end: parses real JUnit XML into a suite
and writes real HTML / Markdown / JSON reports to tmp files, asserting both the
rendered summary and the on-disk artifact. Pure file I/O — nothing mocked.
"""

import json

import pytest
from click.testing import CliRunner

from framework.cli.report_commands import report

_JUNIT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Regression" tests="3" time="4.5">
  <testcase name="test_ok" classname="pkg.A" time="1.0"/>
  <testcase name="test_bad" classname="pkg.B" time="2.0">
    <failure message="expected 1 got 2">trace</failure>
  </testcase>
  <testcase name="test_skip" classname="pkg.C" time="0.0">
    <skipped/>
  </testcase>
</testsuite>
"""


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def junit(tmp_path):
    p = tmp_path / "results.xml"
    p.write_text(_JUNIT_XML, encoding="utf-8")
    return p


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


# -------------------------------------------------------------------------- generate


def test_generate_html(runner, junit, tmp_path):
    out = tmp_path / "report.html"
    result = runner.invoke(report, ["generate", "-j", str(junit), "-o", str(out), "-f", "html"])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()
    body = out.read_text()
    assert "<html" in body.lower() and "Regression" in body


def test_generate_markdown(runner, junit, tmp_path):
    out = tmp_path / "REPORT.md"
    result = runner.invoke(report, ["generate", "-j", str(junit), "-o", str(out), "-f", "markdown"])
    _no_crash(result)
    assert out.exists()
    assert "# Test Report: Regression" in out.read_text()


def test_generate_json(runner, junit, tmp_path):
    out = tmp_path / "report.json"
    result = runner.invoke(report, ["generate", "-j", str(junit), "-o", str(out), "-f", "json"])
    _no_crash(result)
    data = json.loads(out.read_text())
    assert data["summary"]["total"] == 3
    assert data["summary"]["failed"] == 1
    assert data["summary"]["skipped"] == 1
    assert data["summary"]["passed"] == 1


def test_generate_missing_input_exits_one(runner, tmp_path):
    result = runner.invoke(report, ["generate", "-j", str(tmp_path / "nope.xml"), "-o", str(tmp_path / "o.html")])
    _no_crash(result)
    assert result.exit_code == 1
    assert "not found" in result.output


def test_generate_malformed_xml_exits_one(runner, tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("this is not xml <<<", encoding="utf-8")
    out = tmp_path / "o.html"
    result = runner.invoke(report, ["generate", "-j", str(bad), "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 1
    assert "Error" in result.output


# --------------------------------------------------------------------------- summary


def test_summary_shows_counts(runner, junit):
    result = runner.invoke(report, ["summary", str(junit)])
    _no_crash(result)
    assert result.exit_code == 0
    # 1 of 3 passed → 33.3% pass rate, and the failing test is listed.
    assert "Total Tests" in result.output
    assert "test_bad" in result.output


def test_summary_missing_file_exits_one(runner, tmp_path):
    result = runner.invoke(report, ["summary", str(tmp_path / "nope.xml")])
    _no_crash(result)
    assert result.exit_code == 1


# ------------------------------------------------------------------------------ list


def test_list_formats(runner):
    result = runner.invoke(report, ["list"])
    _no_crash(result)
    assert "HTML" in result.output and "Markdown" in result.output and "JSON" in result.output
