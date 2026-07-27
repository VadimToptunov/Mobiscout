"""Behaviour tests for the `mobiscout execute` CLI group (framework/cli/execute_commands.py).

Two layers are covered:
  * TestMonitor — the pure pytest-output parser/renderer — is driven directly
    with real pytest-style lines and asserted on (counts, current test, bars).
  * The CLI commands (run / parallel / stress / watch) shell out to pytest, so
    only that subprocess boundary is faked; the command's own control flow,
    exit-code propagation and error branches run for real.
"""

from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from framework.cli import execute_commands as ec
from framework.cli.execute_commands import execute

# Reference the monitor via the module (importing the name would make pytest try
# to collect the `TestMonitor` class as a test suite).
Monitor = ec.TestMonitor


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


# --- TestMonitor (pure logic) ------------------------------------------------


def test_monitor_counts_pass_fail_skip():
    m = Monitor()
    m.update_progress("test_alpha PASSED")
    m.update_progress("test_beta FAILED")
    m.update_progress("test_gamma SKIPPED")
    assert m.passed == 1
    assert m.failed == 1
    assert m.skipped == 1
    # Last extracted test name is remembered as "current".
    assert m.current_test == "test_gamma"


def test_monitor_history_capped_and_named():
    m = Monitor()
    for i in range(15):
        m.update_progress(f"test_num{i} PASSED")
    # history stores entries, and each carries a rendered status.
    assert m.test_history
    assert all(entry["status"] == "✅ PASSED" for entry in m.test_history)


def test_monitor_progress_bar_percentage():
    m = Monitor()
    bar = m._progress_bar(1, 4)
    assert "25%" in bar
    assert m._progress_bar(0, 0) == ""  # no divide-by-zero


def test_monitor_renders_without_history():
    m = Monitor()
    panel = m.render_history()
    # Rich Panel object; its renderable says there is nothing yet.
    assert "No tests executed yet" in str(panel.renderable)


# --- run ---------------------------------------------------------------------


def test_run_standard_propagates_exit_code(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(ec.subprocess, "run", lambda cmd, **k: SimpleNamespace(returncode=0))
    result = runner.invoke(execute, ["run", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0


def test_run_standard_nonzero_exit(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(ec.subprocess, "run", lambda cmd, **k: SimpleNamespace(returncode=3))
    result = runner.invoke(execute, ["run", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 3


def test_run_live_monitor(runner, tmp_path, monkeypatch):
    class FakeProc:
        def __init__(self):
            self.stdout = iter(["tests/test_x.py::test_one PASSED\n", "tests/test_y.py::test_two FAILED\n"])
            self.returncode = 1

        def wait(self):
            return self.returncode

    monkeypatch.setattr(ec.subprocess, "Popen", lambda *a, **k: FakeProc())
    result = runner.invoke(execute, ["run", str(tmp_path), "--live"])
    _no_crash(result)
    assert result.exit_code == 1


# --- parallel ----------------------------------------------------------------


def test_parallel_runs(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(ec.subprocess, "run", lambda cmd, **k: SimpleNamespace(returncode=0))
    result = runner.invoke(execute, ["parallel", str(tmp_path), "-w", "2"])
    _no_crash(result)
    assert result.exit_code == 0


def test_parallel_missing_xdist_aborts(runner, tmp_path, monkeypatch):
    def _missing(cmd, **k):
        raise FileNotFoundError("no xdist")

    monkeypatch.setattr(ec.subprocess, "run", _missing)
    result = runner.invoke(execute, ["parallel", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code != 0
    assert "pytest-xdist not installed" in result.output


# --- stress ------------------------------------------------------------------


def test_stress_zero_duration_summary(runner, tmp_path):
    # duration 0 => the loop body never runs; the command still prints a summary.
    result = runner.invoke(execute, ["stress", str(tmp_path), "-d", "0"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Stress test complete" in result.output
    assert "Iterations: 0" in result.output


def test_stress_parses_one_iteration(runner, tmp_path, monkeypatch):
    # Force exactly one iteration and feed a pytest summary line to parse.
    times = iter([0.0, 0.0, 100.0, 100.0])
    monkeypatch.setattr(ec.time, "time", lambda: next(times))
    monkeypatch.setattr(ec.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(
        ec.subprocess, "run", lambda cmd, **k: SimpleNamespace(returncode=0, stdout="3 passed, 1 failed")
    )
    result = runner.invoke(execute, ["stress", str(tmp_path), "-d", "5"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Iterations: 1" in result.output
    assert "Total passed: 3" in result.output
    assert "Total failed: 1" in result.output


# --- watch -------------------------------------------------------------------


def test_watch_no_test_files_returns(runner, tmp_path):
    # Existing but empty directory => no *.py files => early, clean return.
    result = runner.invoke(execute, ["watch", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No Python test files found" in result.output


def test_watch_runs_then_stops_on_interrupt(runner, tmp_path, monkeypatch):
    (tmp_path / "test_sample.py").write_text("def test_x():\n    assert True\n")
    monkeypatch.setattr(ec.subprocess, "run", lambda cmd, **k: SimpleNamespace(returncode=0))

    def _stop(*_a):
        raise KeyboardInterrupt

    monkeypatch.setattr(ec.time, "sleep", _stop)
    result = runner.invoke(execute, ["watch", str(tmp_path), "-i", "1"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Changes detected" in result.output
    assert "Watch mode stopped" in result.output
