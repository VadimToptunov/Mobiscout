"""Behaviour tests for the ``parallel`` CLI group (parallel test execution).

The sharding, benchmark and shard-file commands are pure in-process logic and run
for real over tmp_path test trees. ``parallel run`` shells out to pytest and a
ThreadPool executor, so its executor is stubbed to a canned result — the command's
own shard-building, summary rendering and exit-code logic still run for real.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

import framework.cli.parallel_commands as pc
from framework.cli.parallel_commands import parallel


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _test_tree(tmp_path: Path, n: int = 4) -> Path:
    d = tmp_path / "tests"
    d.mkdir()
    for i in range(n):
        (d / f"test_{i}.py").write_text(f"def test_{i}():\n    assert True\n", encoding="utf-8")
    return d


def test_create_shards_partitions_all_tests(runner, tmp_path):
    tree = _test_tree(tmp_path, 6)
    out = tmp_path / "shards"
    result = runner.invoke(parallel, ["create-shards", str(tree), "3", "--strategy", "balanced", "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    shard_files = sorted(out.glob("shard_*.txt"))
    assert len(shard_files) == 3
    # Every discovered test appears in exactly one shard file.
    written = "\n".join(f.read_text() for f in shard_files)
    for i in range(6):
        assert f"test_{i}" in written


@pytest.mark.parametrize("strategy", ["round_robin", "balanced", "by_file"])
def test_create_shards_accepts_each_strategy(runner, tmp_path, strategy):
    tree = _test_tree(tmp_path, 4)
    result = runner.invoke(parallel, ["create-shards", str(tree), "2", "--strategy", strategy])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Test Shards" in result.output


def test_benchmark_reports_speedup_for_each_strategy(runner):
    result = runner.invoke(parallel, ["benchmark", "-w", "4", "--test-count", "40"])
    _no_crash(result)
    assert result.exit_code == 0
    # All three strategies are benchmarked and a best is chosen.
    assert "Round Robin" in result.output
    assert "Balanced" in result.output
    assert "By File" in result.output
    assert "Best:" in result.output


def test_on_devices_handles_no_devices(runner, tmp_path, monkeypatch):
    # No real devices in CI: DeviceManager returns an empty list -> clean message.
    monkeypatch.setattr(pc.DeviceManager, "get_available_devices", lambda self: [])
    tree = _test_tree(tmp_path)
    result = runner.invoke(parallel, ["on-devices", str(tree), "--platform", "android"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No android devices found" in result.output


def test_on_devices_lists_discovered_devices(runner, tmp_path, monkeypatch):
    fake = [
        {"name": "Pixel_7", "platform": "android", "platform_version": "14", "status": "online"},
        {"name": "iPhone15", "platform": "ios", "os_version": "17", "status": "online"},
    ]
    monkeypatch.setattr(pc.DeviceManager, "get_available_devices", lambda self: fake)
    tree = _test_tree(tmp_path)
    result = runner.invoke(parallel, ["on-devices", str(tree), "--platform", "android"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Pixel_7" in result.output
    # iOS device filtered out by --platform android.
    assert "iPhone15" not in result.output


def test_run_missing_dir_returns_cleanly(runner, tmp_path):
    result = runner.invoke(parallel, ["run", str(tmp_path / "does_not_exist")])
    _no_crash(result)
    assert "Test directory not found" in result.output


class _FakeExecutor:
    """Stand-in for ParallelExecutor so `parallel run` never spawns pytest."""

    def __init__(self, max_workers, pytest_args):
        self.max_workers = max_workers

    def execute_shards(self, shards, cwd, progress_callback=None):
        if progress_callback:
            progress_callback(len(shards), len(shards))
        return []  # no shard results

    def generate_summary(self, results):
        return "SUMMARY: 4 passed"

    def aggregate_results(self, results):
        return {"failed": 0, "errors": 0}


class _FailingExecutor(_FakeExecutor):
    def aggregate_results(self, results):
        return {"failed": 2, "errors": 0}


def test_run_success_exits_zero(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "ParallelExecutor", _FakeExecutor)
    tree = _test_tree(tmp_path, 4)
    result = runner.invoke(parallel, ["run", str(tree), "-w", "2"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "SUMMARY" in result.output


def test_run_with_failures_exits_nonzero(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "ParallelExecutor", _FailingExecutor)
    tree = _test_tree(tmp_path, 4)
    result = runner.invoke(parallel, ["run", str(tree), "-w", "2"])
    _no_crash(result)
    assert result.exit_code == 1
