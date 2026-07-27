"""Tests for framework.testing.load_tester.

Guards the load-test orchestration and result math without touching real devices
or the test runner: predefined-profile lookup, the end-to-end run() over a
single virtual user with the per-iteration test execution stubbed, the
statistics aggregation (percentiles/throughput/error collection) in
_generate_results, the fail-fast critical-error heuristic, and JSON persistence.
"""

import json
from datetime import datetime, timedelta

import pytest

from framework.testing.load_tester import (
    LoadProfile,
    LoadTestConfig,
    LoadTester,
    LoadTestResult,
)


def _config(profile: LoadProfile) -> LoadTestConfig:
    return LoadTestConfig(test_path="tests/dummy_test.py", profile=profile, max_workers=2)


def test_get_profile_known_and_unknown():
    smoke = LoadTester.get_profile("smoke")
    assert smoke.virtual_users == 1
    with pytest.raises(ValueError):
        LoadTester.get_profile("nonexistent")


def test_list_profiles_covers_all():
    names = {p.name for p in LoadTester.list_profiles()}
    assert "Smoke Test" in names and "Stress Test" in names
    assert len(LoadTester.list_profiles()) == len(LoadTester.PROFILES)


def test_run_executes_iterations_and_aggregates(monkeypatch):
    profile = LoadProfile(
        name="unit",
        description="one user, one iteration",
        virtual_users=1,
        duration_seconds=60,  # large so the time-budget loop doesn't exit first
        ramp_up_seconds=0,
        think_time_seconds=0.0,
        iterations=1,
    )
    tester = LoadTester(_config(profile))

    calls = []

    def fake_execute(user_id):
        calls.append(user_id)
        return True

    monkeypatch.setattr(tester, "_execute_test", fake_execute)

    result = tester.run()
    assert calls == [0]  # exactly one iteration for the single user
    assert result.total_tests == 1
    assert result.passed_tests == 1
    assert result.failed_tests == 0
    assert result.throughput > 0
    assert result.profile_name == "unit"


def test_run_records_failures(monkeypatch):
    profile = LoadProfile(
        name="failing",
        description="failing iteration",
        virtual_users=1,
        duration_seconds=60,
        think_time_seconds=0.0,
        iterations=1,
    )
    tester = LoadTester(_config(profile))
    monkeypatch.setattr(tester, "_execute_test", lambda uid: False)

    result = tester.run()
    assert result.total_tests == 1
    assert result.failed_tests == 1
    assert result.passed_tests == 0


def test_generate_results_statistics():
    profile = LoadTester.get_profile("smoke")
    tester = LoadTester(_config(profile))
    tester.response_times = [0.1, 0.2, 0.3, 0.4, 0.5]
    tester.results = [
        {
            "user_id": 0,
            "iterations": 3,
            "results": [
                {"success": True, "response_time": 0.1, "iteration": 0},
                {"success": False, "response_time": 0.2, "iteration": 1, "error": "boom"},
                {"success": True, "response_time": 0.3, "iteration": 2},
            ],
        }
    ]
    start = datetime(2024, 1, 1, 0, 0, 0)
    end = start + timedelta(seconds=10)
    result = tester._generate_results(start, end)

    assert result.total_tests == 3
    assert result.passed_tests == 2
    assert result.failed_tests == 1
    assert result.min_response_time == 0.1
    assert result.max_response_time == 0.5
    assert result.avg_response_time == pytest.approx(0.3)
    assert result.throughput == pytest.approx(0.3)  # 3 tests / 10s
    assert len(result.errors) == 1
    assert result.errors[0]["error"] == "boom"
    assert result.error_tests == 1


def test_generate_results_empty_is_zeroed():
    tester = LoadTester(_config(LoadTester.get_profile("smoke")))
    start = datetime(2024, 1, 1)
    result = tester._generate_results(start, start + timedelta(seconds=5))
    assert result.total_tests == 0
    assert result.avg_response_time == 0
    assert result.throughput == 0


def test_has_critical_errors_threshold():
    tester = LoadTester(_config(LoadTester.get_profile("smoke")))
    # fewer than 10 results -> never critical
    tester.results = [{"success": False}] * 5
    assert tester._has_critical_errors() is False
    # 6 of last 10 failed -> critical
    tester.results = [{"success": False}] * 6 + [{"success": True}] * 4
    assert tester._has_critical_errors() is True
    # only 4 of last 10 failed -> not critical
    tester.results = [{"success": False}] * 4 + [{"success": True}] * 6
    assert tester._has_critical_errors() is False


def test_save_results_writes_json(tmp_path):
    tester = LoadTester(_config(LoadTester.get_profile("smoke")))
    result = LoadTestResult(
        profile_name="Smoke Test",
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 1, 0, 0, 5),
        duration_seconds=5.0,
        total_tests=1,
        passed_tests=1,
        failed_tests=0,
        skipped_tests=0,
        error_tests=0,
        total_requests=1,
        avg_response_time=0.2,
        min_response_time=0.2,
        max_response_time=0.2,
        p50_response_time=0.2,
        p95_response_time=0.2,
        p99_response_time=0.2,
        throughput=0.2,
    )
    out = tmp_path / "nested" / "result.json"
    tester.save_results(result, out)
    data = json.loads(out.read_text())
    assert data["profile_name"] == "Smoke Test"
    assert data["total_tests"] == 1
    assert data["throughput"] == 0.2
