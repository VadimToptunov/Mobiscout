"""Behaviour tests for the ``load`` CLI group (load testing + profiling).

``load profiles`` and ``load compare`` are pure and run for real. ``load profile``
executes the real in-process profiler over a dummy function. ``load run`` drives
real devices/threads, so only ``LoadTester.run`` is stubbed to a canned result —
the command's own config-building, results table and JSON persistence run for real.
This also guards the ZeroDivisionError regression when a run executed 0 tests.
"""

import json
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner

import framework.cli.load_commands as lc
from framework.cli.load_commands import load, _pct
from framework.testing.load_tester import LoadTestResult


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _result(total=10, passed=8, failed=2) -> LoadTestResult:
    now = datetime.now()
    return LoadTestResult(
        profile_name="Smoke Test",
        start_time=now,
        end_time=now + timedelta(seconds=5),
        duration_seconds=5.0,
        total_tests=total,
        passed_tests=passed,
        failed_tests=failed,
        skipped_tests=0,
        error_tests=0,
        total_requests=total,
        avg_response_time=0.12,
        min_response_time=0.05,
        max_response_time=0.30,
        p50_response_time=0.10,
        p95_response_time=0.28,
        p99_response_time=0.30,
        throughput=2.0,
        errors=[],
    )


def test_pct_is_zero_safe():
    assert _pct(0, 0) == 0.0
    assert _pct(5, 10) == 50.0


def test_profiles_lists_predefined_profiles(runner):
    result = runner.invoke(load, ["profiles"])
    _no_crash(result)
    assert result.exit_code == 0
    # Predefined profiles are surfaced by name.
    assert "Smoke Test" in result.output
    assert "Stress Test" in result.output


def test_run_renders_results_and_saves_json(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(lc.LoadTester, "run", lambda self, progress_callback=None: _result())
    test_file = tmp_path / "test_x.py"
    test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    out = tmp_path / "results"

    result = runner.invoke(load, ["run", str(test_file), "--profile", "smoke", "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Total Tests" in result.output
    saved = out / "load_test_results.json"
    assert saved.exists()
    assert json.loads(saved.read_text())["total_tests"] == 10


def test_run_with_zero_tests_does_not_crash(runner, tmp_path, monkeypatch):
    # Regression: the results table divided passed/failed by total_tests and blew
    # up with ZeroDivisionError when a run executed no tests at all.
    monkeypatch.setattr(lc.LoadTester, "run", lambda self, progress_callback=None: _result(total=0, passed=0, failed=0))
    test_file = tmp_path / "test_x.py"
    test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")

    result = runner.invoke(load, ["run", str(test_file), "--profile", "smoke"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "0.0%" in result.output


def test_run_overrides_are_applied(runner, tmp_path, monkeypatch):
    captured = {}

    def fake_run(self, progress_callback=None):
        captured["users"] = self.config.profile.virtual_users
        captured["duration"] = self.config.profile.duration_seconds
        return _result()

    monkeypatch.setattr(lc.LoadTester, "run", fake_run)
    test_file = tmp_path / "test_x.py"
    test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")

    result = runner.invoke(load, ["run", str(test_file), "--profile", "smoke", "--users", "9", "--duration", "3"])
    _no_crash(result)
    assert captured == {"users": 9, "duration": 3}


def test_profile_runs_real_profiler(runner, tmp_path):
    test_file = tmp_path / "test_x.py"
    test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    out = tmp_path / "profile.json"

    result = runner.invoke(load, ["profile", str(test_file), "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Profile Results" in result.output
    assert out.exists()
    saved = json.loads(out.read_text())
    assert "duration_seconds" in saved


def test_compare_reports_regression(runner, tmp_path):
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    baseline.write_text(json.dumps({"duration_seconds": 1.0}), encoding="utf-8")
    current.write_text(json.dumps({"duration_seconds": 2.0}), encoding="utf-8")  # slower -> regression

    result = runner.invoke(load, ["compare", str(baseline), str(current)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "regression" in result.output.lower()


def test_compare_reports_improvement(runner, tmp_path):
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    baseline.write_text(json.dumps({"duration_seconds": 2.0}), encoding="utf-8")
    current.write_text(json.dumps({"duration_seconds": 1.0}), encoding="utf-8")  # faster -> improvement

    result = runner.invoke(load, ["compare", str(baseline), str(current)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "improvement" in result.output.lower()
