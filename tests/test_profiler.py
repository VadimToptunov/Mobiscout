"""Coverage for the performance profiler: CPU (cProfile) + memory (tracemalloc)
+ time profiling of a callable, profile comparison, and JSON/HTML export.
Previously 0% covered. Profiling a trivial function keeps it fast."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from framework.testing.profiler import PerformanceProfiler, ProfileResult, ProfilerConfig


def _work():
    # A little real work so the CPU/memory profiles have something to report.
    return sum(i * i for i in range(1000))


@pytest.fixture()
def profiler():
    return PerformanceProfiler(ProfilerConfig())


def test_profiler_config_defaults():
    cfg = ProfilerConfig()
    assert cfg.profile_cpu and cfg.profile_memory and cfg.profile_time
    assert cfg.sort_by == "cumulative"


def test_profile_result_to_dict_is_serializable():
    now = datetime.now()
    result = ProfileResult("t.py", now, now + timedelta(seconds=1), 1.0)
    d = result.to_dict()
    assert d["test_path"] == "t.py"
    assert d["start_time"] == now.isoformat()
    json.dumps(d)  # fully serializable


def test_profile_test_full_config(profiler):
    result = profiler.profile_test(Path("mytest.py"), _work)
    assert isinstance(result, ProfileResult)
    assert result.test_path == "mytest.py"
    assert result.duration_seconds >= 0
    assert result.time_profile["success"] is True
    assert "top_functions" in result.cpu_profile
    assert "total_size_bytes" in result.memory_profile


def test_profile_test_records_failure_and_reports_progress():
    profiler = PerformanceProfiler(ProfilerConfig())
    messages = []

    def boom():
        raise ValueError("kaboom")

    result = profiler.profile_test(Path("t.py"), boom, progress_callback=messages.append)
    assert result.time_profile["success"] is False
    assert any("failed" in m.lower() for m in messages)
    assert any("Starting profiling" in m for m in messages)


def test_profile_test_can_disable_cpu_and_memory():
    profiler = PerformanceProfiler(ProfilerConfig(profile_cpu=False, profile_memory=False))
    result = profiler.profile_test(Path("t.py"), _work)
    assert result.cpu_profile is None
    assert result.memory_profile is None
    assert result.time_profile is not None  # time is always captured


def test_compare_profiles_flags_regression(profiler):
    now = datetime.now()
    baseline = ProfileResult("t.py", now, now, 1.0, memory_profile={"total_size_mb": 10.0})
    slower = ProfileResult("t.py", now, now, 2.0, memory_profile={"total_size_mb": 15.0})
    cmp = profiler.compare_profiles(baseline, slower)
    assert cmp["changes"]["duration"]["regression"] is True
    assert cmp["changes"]["duration"]["percentage"] == pytest.approx(100.0)
    assert cmp["changes"]["memory"]["regression"] is True


def test_compare_profiles_no_regression(profiler):
    now = datetime.now()
    baseline = ProfileResult("t.py", now, now, 2.0)
    faster = ProfileResult("t.py", now, now, 1.0)
    cmp = profiler.compare_profiles(baseline, faster)
    assert cmp["changes"]["duration"]["regression"] is False
    assert "memory" not in cmp["changes"]  # no memory profiles supplied


def test_save_profile_writes_json(profiler, tmp_path):
    now = datetime.now()
    result = ProfileResult("t.py", now, now, 0.5)
    out = tmp_path / "sub" / "profile.json"
    profiler.save_profile(result, out)
    assert json.loads(out.read_text())["test_path"] == "t.py"


def test_generate_report_writes_html(profiler, tmp_path):
    now = datetime.now()
    result = ProfileResult("cool_test.py", now, now, 0.5, time_profile={"success": True})
    out = tmp_path / "report.html"
    profiler.generate_report(result, out)
    html = out.read_text()
    assert "<!DOCTYPE html>" in html
    assert "cool_test.py" in html
