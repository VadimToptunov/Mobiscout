"""Consolidation guards for the canonical domain value objects.

These assert that the formerly-duplicated ``ReportFormat`` / ``TestResult`` /
``TestSuiteResult`` types are now a *single* definition shared by identity across
subsystems (reporting, dashboard, execution), and that a value produced by one
subsystem is consumed by another without a field- or status-mismatch.
"""

import json
from datetime import datetime

from framework import domain
from framework.domain import ReportFormat, TestResult, TestStatus, TestSuiteResult

# --- ReportFormat: one canonical enum, shared by identity ---------------------


def test_report_format_is_single_canonical_across_reporting():
    from framework.reporting.base_reporter import ReportFormat as BaseRF
    from framework.reporting.report_generator import ReportFormat as GenRF
    from framework.reporting.unified_reporter import ReportFormat as UnifiedRF

    assert BaseRF is ReportFormat
    assert GenRF is ReportFormat
    assert UnifiedRF is ReportFormat
    # reporting.__init__ re-exports both the plain and the "Base" alias.
    from framework.reporting import BaseReportFormat, ReportFormat as PkgRF

    assert PkgRF is ReportFormat
    assert BaseReportFormat is ReportFormat


def test_report_format_is_superset_and_string_valued():
    # Union of every subsystem's former members.
    names = {m.name for m in ReportFormat}
    assert {"HTML", "JSON", "ALLURE", "JUNIT", "TEXT", "XML", "MARKDOWN", "PDF"} <= names
    # str-based, like the other domain enums.
    assert ReportFormat.HTML == "html"
    assert ReportFormat.HTML.value == "html"


# --- TestResult / TestSuiteResult identity -----------------------------------


def test_reporting_result_types_are_the_canonical_ones():
    from framework.reporting.report_generator import (
        TestResult as GenTestResult,
        TestSuiteResult as GenSuite,
    )

    assert GenTestResult is TestResult
    assert GenSuite is TestSuiteResult
    # also reachable via the package root.
    from framework.reporting import TestResult as PkgTR, TestSuiteResult as PkgSuite

    assert PkgTR is TestResult
    assert PkgSuite is TestSuiteResult


def test_dashboard_result_is_a_thin_subclass_of_canonical():
    from framework.dashboard.models import TestResult as DbTestResult

    # Not identity (it adds required persistence fields), but a real subclass so
    # instances ARE canonical TestResults.
    assert issubclass(DbTestResult, TestResult)
    row = DbTestResult(
        id="r1",
        name="test_login",
        status=TestStatus.PASSED,
        duration=0.4,
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        file_path="tests/test_login.py",
    )
    assert isinstance(row, TestResult)


# --- TestStatus shared across the subsystems that carry a status -------------


def test_test_status_is_shared_across_subsystems():
    from framework.dashboard.models import TestStatus as DashboardStatus
    from framework.execution.test_runner import TestResultStatus as RunnerStatus

    assert DashboardStatus is TestStatus
    assert RunnerStatus is TestStatus
    assert domain.TestStatus is TestStatus


# --- producer -> consumer, no field / status mismatch ------------------------


def test_value_produced_for_one_subsystem_is_consumed_by_another():
    """A canonical TestResult built by hand feeds report_generator's JSON
    consumer, and the same status enum round-trips through the dashboard row."""
    from framework.dashboard.models import TestResult as DbTestResult
    from framework.reporting.report_generator import JSONReportGenerator

    result = TestResult(name="test_pay", status=TestStatus.FAILED, duration=1.2, error_message="boom")
    suite = TestSuiteResult(name="Checkout", tests=[result])

    # Consumer #1: the reporting JSON generator reads .status/.name/.error_message.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "r.json"
        JSONReportGenerator().generate(suite, out)
        data = json.loads(out.read_text(encoding="utf-8"))

    payload = data["tests"][0]
    assert payload["name"] == "test_pay"
    assert payload["status"] == "failed"  # TestStatus serialized to its wire string
    assert payload["error_message"] == "boom"

    # Consumer #2: the dashboard row accepts the very same TestStatus member
    # (no adapter, no status-string mismatch) and serializes identically.
    row = DbTestResult(
        id="r1",
        name=result.name,
        status=result.status,
        duration=result.duration,
        timestamp=datetime(2024, 1, 1),
        file_path="f.py",
        error_message=result.error_message,
    )
    assert row.to_dict()["status"] == "failed"
    assert row.status is TestStatus.FAILED
