"""Behavior tests for the `perf` CLI group.

The device-touching profiling body is stubbed in the module itself (it never
talks to a real device), so `profile` is a pure control-flow command that we can
drive directly. `report` and `compare` run the real PerformanceAnalyzer, which
starts with no stored metrics, so the "profile not found" branches (which raise
click.Abort -> exit 1) are the real, assertable behavior here.
"""

import pytest
from click.testing import CliRunner

from framework.analysis.performance_analyzer import PerformanceAnalyzer, PerformanceMetrics
from framework.cli import perf_commands
from framework.cli.perf_commands import perf


@pytest.fixture()
def runner():
    return CliRunner()


def _seed(monkeypatch, profiles):
    """Make `PerformanceAnalyzer()` inside the command return a real analyzer
    pre-populated (through the real analyze_metrics API) with the given profiles.

    This is not a stub of the code under test — the command still runs the real
    report/compare rendering over real analyzer state; we only supply the metrics
    that a live device would normally have collected.
    """
    analyzer = PerformanceAnalyzer()
    for name, metrics in profiles.items():
        analyzer.analyze_metrics(metrics, name)
    monkeypatch.setattr(perf_commands, "PerformanceAnalyzer", lambda: analyzer)
    return analyzer


def _metrics(**overrides) -> PerformanceMetrics:
    base = dict(
        app_start_time=1.2,
        memory_usage=80.0,
        cpu_usage=20.0,
        network_requests=10,
        avg_request_time=120.0,
        fps=60.0,
        battery_drain=3.0,
    )
    base.update(overrides)
    return PerformanceMetrics(**base)


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def test_profile_completes_without_output(runner):
    result = runner.invoke(perf, ["profile", "-d", "emulator-5554", "-a", "com.example", "--duration", "1"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Profile complete" in result.output


def test_profile_reports_saved_with_output(runner, tmp_path):
    out = tmp_path / "profile.json"
    result = runner.invoke(perf, ["profile", "-d", "dev1", "-a", "com.example", "--duration", "1", "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Profile saved" in result.output


def test_report_unknown_profile_aborts(runner):
    result = runner.invoke(perf, ["report", "-p", "does-not-exist"])
    _no_crash(result)
    # Missing profile -> click.Abort -> non-zero exit.
    assert result.exit_code != 0
    assert "not found" in result.output


def test_compare_unknown_profiles_aborts(runner):
    result = runner.invoke(perf, ["compare", "-b", "base", "-c", "curr"])
    _no_crash(result)
    assert result.exit_code != 0
    assert "not found" in result.output


def test_profile_requires_device_and_app(runner):
    # Both -d and -a are required; omitting them is a usage error, not a crash.
    result = runner.invoke(perf, ["profile"])
    _no_crash(result)
    assert result.exit_code == 2


def test_report_renders_metrics_table(runner, monkeypatch):
    _seed(monkeypatch, {"good": _metrics()})
    result = runner.invoke(perf, ["report", "-p", "good"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Performance Metrics" in result.output
    assert "App Startup" in result.output


def test_report_lists_detected_issues(runner, monkeypatch):
    # Values above the analyzer thresholds produce real PerformanceIssue objects.
    _seed(monkeypatch, {"bad": _metrics(app_start_time=6.0, memory_usage=700.0, cpu_usage=95.0)})
    result = runner.invoke(perf, ["report", "-p", "bad"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Performance Issues" in result.output


def test_compare_reports_regression(runner, monkeypatch):
    _seed(
        monkeypatch,
        {
            "base": _metrics(),
            "curr": _metrics(app_start_time=3.0, memory_usage=200.0, cpu_usage=60.0, fps=40.0, battery_drain=8.0),
        },
    )
    result = runner.invoke(perf, ["compare", "-b", "base", "-c", "curr"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Performance Comparison" in result.output
    # curr is worse across the board -> regressions dominate.
    assert "degraded" in result.output.lower()


def test_compare_reports_improvement(runner, monkeypatch):
    _seed(
        monkeypatch,
        {
            "base": _metrics(app_start_time=3.0, memory_usage=200.0, cpu_usage=60.0),
            "curr": _metrics(app_start_time=1.0, memory_usage=70.0, cpu_usage=15.0),
        },
    )
    result = runner.invoke(perf, ["compare", "-b", "base", "-c", "curr"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "improved" in result.output.lower()
