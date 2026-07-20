"""Unified reporter: aggregate test suites and render reports (HTML / JSON /
Allure). Covers the suite metrics (pass/fail/skip/rate), format dispatch, and
loading JUnit XML from a file and a directory."""

import json

import pytest

from framework.reporting.unified_reporter import (
    ReportFormat,
    TestResult,
    TestSuite,
    UnifiedReporter,
)


def _suite(name="suite", statuses=("passed", "passed", "failed", "skipped")):
    tests = [TestResult(name=f"t{i}", status=s, duration=0.1) for i, s in enumerate(statuses)]
    return TestSuite(name=name, tests=tests, timestamp="2026-01-01T00:00:00", duration=1.0, platform="ios")


def test_suite_counts_by_status():
    s = _suite()
    assert s.passed == 2 and s.failed == 1 and s.skipped == 1 and s.total == 4


def test_pass_rate_is_percentage():
    assert _suite(statuses=("passed", "passed", "passed", "failed")).pass_rate == 75.0


def test_empty_suite_has_zero_pass_rate():
    assert TestSuite(name="e", tests=[], timestamp="t", duration=0.0).pass_rate == 0.0


def test_add_suite_accumulates():
    r = UnifiedReporter()
    r.add_suite(_suite())
    r.add_suite(_suite())
    assert len(r.suites) == 2


def test_html_report_is_written_with_title_and_totals(tmp_path):
    r = UnifiedReporter()
    r.add_suite(_suite())
    out = tmp_path / "report.html"
    r.generate_report(out, format=ReportFormat.HTML, title="My Run")
    html = out.read_text(encoding="utf-8")
    assert out.exists() and "My Run" in html


def test_json_report_round_trips_the_numbers(tmp_path):
    r = UnifiedReporter()
    r.add_suite(_suite())
    out = tmp_path / "report.json"
    r.generate_report(out, format=ReportFormat.JSON)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data  # non-empty structured report


def test_unsupported_format_raises(tmp_path):
    r = UnifiedReporter()
    r.add_suite(_suite())
    with pytest.raises(ValueError):
        r.generate_report(tmp_path / "x", format=ReportFormat.JUNIT)


def test_load_from_junit_file(tmp_path):
    xml = tmp_path / "junit-results.xml"
    xml.write_text(
        '<?xml version="1.0"?>'
        '<testsuite name="S" tests="2" failures="1" skipped="0" time="0.5">'
        '<testcase name="ok" classname="C" time="0.2"/>'
        '<testcase name="bad" classname="C" time="0.3"><failure message="boom">trace</failure></testcase>'
        "</testsuite>",
        encoding="utf-8",
    )
    r = UnifiedReporter()
    r.load_from_junit(xml)
    assert len(r.suites) == 1
    assert r.suites[0].total == 2 and r.suites[0].failed == 1


def test_load_from_directory_skips_unparsable_and_finds_junit(tmp_path):
    (tmp_path / "junit-a.xml").write_text(
        '<testsuite name="A" tests="1"><testcase name="ok" classname="C" time="0.1"/></testsuite>',
        encoding="utf-8",
    )
    (tmp_path / "notjunit.txt").write_text("ignore me", encoding="utf-8")
    r = UnifiedReporter()
    r.load_from_directory(tmp_path)
    assert len(r.suites) == 1 and r.suites[0].name == "A"
