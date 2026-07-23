"""Regression test for `mobiscout dashboard import-results`.

The command parsed JUnit XML into `reporting.unified_reporter.TestResult` but
then handed those straight to `DashboardDB.add_test_result`, which expects the
unrelated `dashboard.models.TestResult` (enum status, id/timestamp/file_path).
It was dead-on-arrival: the first row would raise AttributeError on
`result.status.value` / missing `.id`. This drives the command end-to-end over a
tmp JUnit file and asserts the rows actually land in the DB.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.dashboard_commands import dashboard
from framework.dashboard.database import DashboardDB

_JUNIT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="SmokeSuite" timestamp="2026-07-23T10:00:00" time="1.5" tests="2">
  <testcase name="test_login" classname="app.LoginTest" time="0.5"/>
  <testcase name="test_checkout" classname="app.CheckoutTest" time="1.0">
    <failure message="assert 1 == 2">stacktrace here</failure>
  </testcase>
</testsuite>
"""


@pytest.fixture()
def runner():
    return CliRunner()


def test_import_results_persists_rows(runner, tmp_path):
    junit = tmp_path / "results.xml"
    junit.write_text(_JUNIT_XML, encoding="utf-8")

    result = runner.invoke(
        dashboard,
        ["import-results", "--junit-xml", str(junit), "--repo", str(tmp_path)],
    )

    # Must not crash (the old code raised on the first result).
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"
    assert result.exit_code == 0, result.output

    # Both testcases should be stored, with the failure mapped to FAILED.
    db = DashboardDB(tmp_path / ".dashboard.db")
    stored = db.get_test_results(limit=100)
    # The parser qualifies each test with its classname.
    names = {r.name for r in stored}
    assert names == {"app.LoginTest.test_login", "app.CheckoutTest.test_checkout"}
    by_name = {r.name: r for r in stored}
    assert by_name["app.CheckoutTest.test_checkout"].status.value == "failed"
    assert by_name["app.CheckoutTest.test_checkout"].error_message
    assert by_name["app.LoginTest.test_login"].status.value == "passed"
