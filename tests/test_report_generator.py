"""Tests for framework.reporting.report_generator.

Guards report rendering across formats: the HTML/Markdown/JSON generators must
emit files whose content reflects the real suite (counts, pass rate, test names,
error text), the TestSuiteResult aggregate properties must compute correct
counts and pass rate, the unified ReportGenerator must dispatch by format and
reject unsupported ones, and from_junit_xml must map JUnit statuses correctly.
"""

import json
from datetime import datetime, timedelta

import pytest

from framework.domain import TestStatus
from framework.reporting.report_generator import (
    HTMLReportGenerator,
    JSONReportGenerator,
    MarkdownReportGenerator,
    ReportFormat,
    ReportGenerator,
    TestResult,
    TestSuiteResult,
)


def _suite() -> TestSuiteResult:
    start = datetime(2024, 1, 1, 10, 0, 0)
    suite = TestSuiteResult(
        name="Checkout Suite",
        tests=[
            TestResult(name="test_add_to_cart", status=TestStatus.PASSED, duration=1.5),
            TestResult(name="test_pay", status=TestStatus.PASSED, duration=2.0),
            TestResult(
                name="test_login",
                status=TestStatus.FAILED,
                duration=0.8,
                error_message="AssertionError: expected 200",
                test_file="tests/login_test.py",
            ),
            TestResult(name="test_skipme", status=TestStatus.SKIPPED, duration=0.0),
            TestResult(name="test_boom", status=TestStatus.ERROR, duration=0.1),
        ],
        start_time=start,
    )
    suite.end_time = start + timedelta(seconds=4.4)
    return suite


def test_suite_result_aggregates():
    suite = _suite()
    assert suite.total_count == 5
    assert suite.passed_count == 2
    assert suite.failed_count == 1
    assert suite.skipped_count == 1
    assert suite.error_count == 1
    assert suite.pass_rate == pytest.approx(40.0)
    assert suite.duration == pytest.approx(4.4)


def test_pass_rate_zero_when_empty():
    assert TestSuiteResult(name="empty").pass_rate == 0.0


def test_html_report_reflects_suite(tmp_path):
    out = tmp_path / "nested" / "report.html"
    HTMLReportGenerator().generate(_suite(), out)
    html = out.read_text(encoding="utf-8")
    assert "Checkout Suite" in html
    # summary card values
    assert ">5</div>" in html  # total
    assert ">2</div>" in html  # passed
    # a failing test name and its error render
    assert "test_login" in html
    assert "AssertionError: expected 200" in html
    # progress bar built for passed/failed/skipped
    assert "progress-segment passed" in html


def test_markdown_report_reflects_suite(tmp_path):
    out = tmp_path / "report.md"
    MarkdownReportGenerator().generate(_suite(), out)
    md = out.read_text(encoding="utf-8")
    assert "# Test Report: Checkout Suite" in md
    assert "**Pass Rate:** 40.0%" in md
    assert "## ❌ Failed Tests" in md
    assert "AssertionError: expected 200" in md
    # all-tests table has a row per test
    assert md.count("test_add_to_cart") >= 1
    assert "| ❌ | test_login |" in md


def test_json_report_is_accurate(tmp_path):
    out = tmp_path / "report.json"
    JSONReportGenerator().generate(_suite(), out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["name"] == "Checkout Suite"
    assert data["summary"]["total"] == 5
    assert data["summary"]["passed"] == 2
    assert data["summary"]["failed"] == 1
    assert data["summary"]["error"] == 1
    assert data["summary"]["pass_rate"] == pytest.approx(40.0)
    assert len(data["tests"]) == 5
    login = next(t for t in data["tests"] if t["name"] == "test_login")
    assert login["status"] == "failed"
    assert login["error_message"] == "AssertionError: expected 200"


def test_report_generator_dispatches_by_format(tmp_path):
    gen = ReportGenerator()
    suite = _suite()
    html_out = tmp_path / "r.html"
    json_out = tmp_path / "r.json"
    gen.generate(suite, html_out, ReportFormat.HTML)
    gen.generate(suite, json_out, ReportFormat.JSON)
    assert html_out.exists() and "<html" in html_out.read_text(encoding="utf-8")
    assert json.loads(json_out.read_text(encoding="utf-8"))["name"] == "Checkout Suite"


def test_report_generator_rejects_unsupported_format(tmp_path):
    with pytest.raises(ValueError):
        ReportGenerator().generate(_suite(), tmp_path / "r.pdf", ReportFormat.PDF)


def test_from_junit_xml_maps_statuses(tmp_path):
    xml = tmp_path / "junit.xml"
    xml.write_text("""<?xml version="1.0"?>
        <testsuite name="MySuite">
          <testcase name="t_pass" classname="pkg.A" time="1.0"/>
          <testcase name="t_fail" classname="pkg.B" time="2.0">
            <failure message="boom">trace</failure>
          </testcase>
          <testcase name="t_err" classname="pkg.C" time="0.5">
            <error message="kaboom">trace</error>
          </testcase>
          <testcase name="t_skip" classname="pkg.D" time="0.0">
            <skipped/>
          </testcase>
        </testsuite>
        """)
    suite = ReportGenerator.from_junit_xml(xml)
    assert suite.name == "MySuite"
    by_name = {t.name: t for t in suite.tests}
    assert by_name["t_pass"].status == TestStatus.PASSED
    assert by_name["t_fail"].status == TestStatus.FAILED
    assert by_name["t_fail"].error_message == "boom"
    assert by_name["t_err"].status == TestStatus.ERROR
    assert by_name["t_skip"].status == TestStatus.SKIPPED
    assert by_name["t_fail"].duration == pytest.approx(2.0)
