"""The cross-platform kit end to end, device-free: an Android and an iOS crawl of one app in, one
kit out — per-platform reports under platforms/, every target's tests rendered once for both
platforms, and a target with no cross-platform form named instead of dropped."""

import pytest

from framework.crawler.pipeline import build_cross_platform_kit, run_cross_platform_kit
from tests.codegen.test_cross_platform import _crawls


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def _results():
    crawls = _crawls()
    return {
        "android": (crawls["android"], {"package": "com.x", "platform": "android", "app_activity": ".Main"}),
        "ios": (crawls["ios"], {"package": "com.x.ios", "platform": "ios"}),
    }


def test_one_kit_with_per_platform_reports_and_merged_tests(tmp_path):
    summary = build_cross_platform_kit(_results(), str(tmp_path), ["python_pytest", "java_testng", "maestro"])
    assert summary["cross_platform"] and set(summary["platforms"]) == {"android", "ios"}
    for platform in ("android", "ios"):
        assert (tmp_path / "platforms" / platform / "inventory.md").exists()
        assert not (tmp_path / "platforms" / platform / "python_pytest").exists(), "reports only there"
    assert summary["targets"] == ["python_pytest", "java_testng"]
    base = (tmp_path / "python_pytest" / "pages" / "base_page.py").read_text(encoding="utf-8")
    assert "MOBISCOUT_PLATFORM" in base and '"ios": "com.x.ios"' in base
    assert (tmp_path / "java_testng" / "src/test/java/mobiscout/support/Platform.java").exists()
    # Maestro has no cross-platform form: named, not silently dropped.
    assert "maestro" in summary["errors"]
    assert "maestro" in (tmp_path / "generation-report.md").read_text(encoding="utf-8")


def test_a_cross_platform_kit_needs_one_app_per_platform():
    with pytest.raises(ValueError, match="one Android and one iOS"):
        run_cross_platform_kit([{"package": "a", "platform": "android"}, {"package": "b", "platform": "android"}])


def test_the_daemon_exposes_it():
    from framework.cli.daemon_commands import JSONRPCServer

    with pytest.raises(ValueError, match="requires 'package'"):
        JSONRPCServer().handle_kit_generate_cross_platform({"configs": [{"platform": "android"}]})
