"""Regression test for `mobiscout dashboard import-results`.

The command parsed JUnit XML into `reporting.unified_reporter.TestResult` but
then handed those straight to `DashboardDB.add_test_result`, which expects the
unrelated `dashboard.models.TestResult` (enum status, id/timestamp/file_path).
It was dead-on-arrival: the first row would raise AttributeError on
`result.status.value` / missing `.id`. This drives the command end-to-end over a
tmp JUnit file and asserts the rows actually land in the DB.
"""

from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

import framework.cli.dashboard_commands as dash_mod
from framework.cli.dashboard_commands import dashboard
from framework.dashboard.database import DashboardDB
from framework.dashboard.models import TestResult as DbTestResult, TestStatus as DbTestStatus

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


# ---------------------------------------------------------------------------------
# The remaining commands (import-results error path, stats, export, start) were
# largely uncovered. These drive each end-to-end: stats/export run over a DB seeded
# with real rows via the public API; start stubs only the socket-binding server.
# ---------------------------------------------------------------------------------


def _seed_db(repo_path: Path):
    """Populate a dashboard DB with a passing and a flaky/failing test's history."""
    db = DashboardDB(repo_path / ".dashboard.db")
    now = datetime.now()
    # A consistently passing test.
    for i in range(4):
        db.add_test_result(
            DbTestResult(
                id=f"stable-{i}",
                name="suite.StableTest.test_ok",
                status=DbTestStatus.PASSED,
                duration=0.4,
                timestamp=now,
                file_path="results.xml",
            )
        )
    # A frequently failing test.
    for i in range(4):
        db.add_test_result(
            DbTestResult(
                id=f"bad-{i}",
                name="suite.BadTest.test_broken",
                status=DbTestStatus.PASSED if i % 4 == 0 else DbTestStatus.FAILED,
                duration=0.9,
                timestamp=now,
                file_path="results.xml",
                error_message="boom" if i % 4 != 0 else None,
            )
        )
    db.close()


def test_import_results_missing_file_errors(runner, tmp_path):
    # --junit-xml is click.Path(exists=True); a missing file is rejected pre-run.
    result = runner.invoke(
        dashboard,
        ["import-results", "--junit-xml", str(tmp_path / "nope.xml"), "--repo", str(tmp_path)],
    )
    assert result.exit_code != 0


def test_stats_without_db_aborts(runner, tmp_path):
    result = runner.invoke(dashboard, ["stats", "--repo", str(tmp_path)])
    assert result.exit_code != 0
    assert "No dashboard database" in result.output


def test_stats_reports_metrics(runner, tmp_path):
    _seed_db(tmp_path)
    result = runner.invoke(dashboard, ["stats", "--repo", str(tmp_path)])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.output
    assert result.exit_code == 0
    assert "Test Statistics" in result.output
    assert "Total tests:" in result.output


def test_export_json_to_file(runner, tmp_path):
    _seed_db(tmp_path)
    out = tmp_path / "metrics.json"
    result = runner.invoke(dashboard, ["export", "--repo", str(tmp_path), "--format", "json", "-o", str(out)])
    assert result.exit_code == 0, result.output
    import json

    data = json.loads(out.read_text())
    assert data["total_tests"] >= 1
    assert "avg_pass_rate" in data


def test_export_prometheus_to_stdout(runner, tmp_path):
    _seed_db(tmp_path)
    result = runner.invoke(dashboard, ["export", "--repo", str(tmp_path), "--format", "prometheus"])
    assert result.exit_code == 0, result.output
    assert "test_total" in result.output
    assert "# TYPE test_pass_rate gauge" in result.output


def test_export_without_db_aborts(runner, tmp_path):
    result = runner.invoke(dashboard, ["export", "--repo", str(tmp_path)])
    assert result.exit_code != 0
    assert "No dashboard database" in result.output


def test_start_runs_server_without_browser(runner, tmp_path, monkeypatch):
    calls = {}

    class _FakeServer:
        def __init__(self, repo_path):
            calls["repo_path"] = repo_path

        def run(self, host, port):
            calls["run"] = (host, port)  # return immediately instead of serving

    monkeypatch.setattr(dash_mod, "DashboardServer", _FakeServer)
    result = runner.invoke(dashboard, ["start", "--no-browser", "--repo", str(tmp_path), "--port", "9999"])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.output
    assert calls["run"] == ("localhost", 9999)


def test_start_failure_aborts(runner, tmp_path, monkeypatch):
    class _BoomServer:
        def __init__(self, repo_path):
            raise RuntimeError("port in use")

    monkeypatch.setattr(dash_mod, "DashboardServer", _BoomServer)
    result = runner.invoke(dashboard, ["start", "--no-browser", "--repo", str(tmp_path)])
    assert result.exit_code != 0
    assert "Failed to start dashboard" in result.output
