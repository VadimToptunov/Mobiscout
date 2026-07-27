"""Behaviour tests for the test runner (framework/execution/test_runner.py).

The only external I/O is spawning a pytest subprocess; that single call is
stubbed. Everything else runs for real: the JSON-report parsing / status
mapping, the TestResult / TestSuiteResult objects, the aggregate properties
(passed/failed/skipped/error, duration) and to_dict serialization.
"""

import json
import subprocess
from datetime import datetime, timedelta

from framework.domain import TestStatus
from framework.execution import test_runner as tr_mod
from framework.execution.test_runner import TestResult, TestRunner, TestSuiteResult

# --- TestSuiteResult aggregates ---------------------------------------------


def _suite(*statuses):
    start = datetime(2024, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=5)
    tests = [TestResult(name=f"t{i}", status=s, duration_ms=10.0) for i, s in enumerate(statuses)]
    return TestSuiteResult(suite_name="suite", start_time=start, end_time=end, tests=tests)


def test_suite_result_counts_by_status():
    suite = _suite(
        TestStatus.PASSED,
        TestStatus.PASSED,
        TestStatus.FAILED,
        TestStatus.SKIPPED,
        TestStatus.ERROR,
    )
    assert suite.total_tests == 5
    assert suite.passed_tests == 2
    assert suite.failed_tests == 1
    assert suite.skipped_tests == 1
    assert suite.error_tests == 1
    assert suite.duration_seconds == 5.0


def test_suite_result_to_dict_roundtrip():
    suite = _suite(TestStatus.PASSED, TestStatus.FAILED)
    d = suite.to_dict()
    assert d["suite_name"] == "suite"
    assert d["total_tests"] == 2
    assert d["passed_tests"] == 1
    assert d["failed_tests"] == 1
    assert d["duration_seconds"] == 5.0
    assert d["tests"][0]["status"] == "passed"
    assert d["tests"][1]["status"] == "failed"


# --- _parse_pytest_report ----------------------------------------------------


def test_parse_pytest_report_maps_outcomes(tmp_path):
    report = {
        "tests": [
            {"nodeid": "test_a", "outcome": "passed", "duration": 0.5},
            {"nodeid": "test_b", "outcome": "failed", "duration": 1.0, "call": {"longrepr": "boom"}},
            {"nodeid": "test_c", "outcome": "skipped", "duration": 0.0},
            {"nodeid": "test_d", "outcome": "weird", "duration": 0.0},  # unknown -> ERROR
        ]
    }
    path = tmp_path / ".report.json"
    path.write_text(json.dumps(report))

    runner = TestRunner(working_dir=tmp_path)
    results = runner._parse_pytest_report(path)

    assert [r.status for r in results] == [
        TestStatus.PASSED,
        TestStatus.FAILED,
        TestStatus.SKIPPED,
        TestStatus.ERROR,
    ]
    assert results[0].duration_ms == 500.0  # seconds -> ms
    assert results[1].message == "boom"


def test_parse_pytest_report_bad_json_returns_empty(tmp_path):
    path = tmp_path / ".report.json"
    path.write_text("{not json")
    runner = TestRunner(working_dir=tmp_path)
    assert runner._parse_pytest_report(path) == []


# --- run_tests ---------------------------------------------------------------


def test_run_tests_parses_report_after_pytest(tmp_path, monkeypatch):
    report = {"tests": [{"nodeid": "test_ok", "outcome": "passed", "duration": 0.2}]}
    (tmp_path / ".report.json").write_text(json.dumps(report))

    calls = {}

    def fake_run(args, **kwargs):
        calls["args"] = args
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(tr_mod.subprocess, "run", fake_run)

    runner = TestRunner(working_dir=tmp_path)
    suite = runner.run_tests(tmp_path / "tests", framework="pytest")

    assert "pytest" in calls["args"]
    assert suite.total_tests == 1
    assert suite.passed_tests == 1
    assert suite.end_time >= suite.start_time


def test_run_tests_timeout_returns_error_result(tmp_path, monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=1)

    monkeypatch.setattr(tr_mod.subprocess, "run", fake_run)
    runner = TestRunner(working_dir=tmp_path, timeout_seconds=1)
    suite = runner.run_tests(tmp_path, framework="pytest")
    assert suite.total_tests == 1
    assert suite.tests[0].status == TestStatus.ERROR
    assert "timed out" in suite.tests[0].message


def test_run_tests_subprocess_error_returns_error_result(tmp_path, monkeypatch):
    def fake_run(args, **kwargs):
        raise OSError("no python")

    monkeypatch.setattr(tr_mod.subprocess, "run", fake_run)
    runner = TestRunner(working_dir=tmp_path)
    suite = runner.run_tests(tmp_path, framework="pytest")
    assert suite.tests[0].status == TestStatus.ERROR
    assert "no python" in suite.tests[0].message


def test_run_tests_unknown_framework_is_empty(tmp_path):
    runner = TestRunner(working_dir=tmp_path)
    suite = runner.run_tests(tmp_path, framework="junit")
    assert suite.total_tests == 0


# --- run_test (single) -------------------------------------------------------


def test_run_test_passed(tmp_path, monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(tr_mod.subprocess, "run", fake_run)
    runner = TestRunner(working_dir=tmp_path)
    result = runner.run_test("test_login", test_path=tmp_path / "t.py")
    assert result.status == TestStatus.PASSED
    assert result.name == "test_login"
    assert result.duration_ms >= 0


def test_run_test_failed_captures_output(tmp_path, monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="assert failed", stderr="traceback")

    monkeypatch.setattr(tr_mod.subprocess, "run", fake_run)
    runner = TestRunner(working_dir=tmp_path)
    result = runner.run_test("test_x", test_path=tmp_path / "t.py")
    assert result.status == TestStatus.FAILED
    assert result.message == "assert failed"
    assert result.stacktrace == "traceback"


def test_run_test_timeout(tmp_path, monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=2)

    monkeypatch.setattr(tr_mod.subprocess, "run", fake_run)
    runner = TestRunner(working_dir=tmp_path, timeout_seconds=2)
    result = runner.run_test("test_x", test_path=tmp_path / "t.py")
    assert result.status == TestStatus.ERROR
    assert result.duration_ms == 2000


def test_run_test_unsupported_framework(tmp_path):
    runner = TestRunner(working_dir=tmp_path)
    result = runner.run_test("test_x", test_path=tmp_path / "t.py", framework="xctest")
    assert result.status == TestStatus.ERROR
    assert "Unsupported framework: xctest" in result.message
