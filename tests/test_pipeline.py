"""Parameterized pipeline: config in, artifact kit out. Driven with the fake
crawler driver so the whole crawl→kit path runs without a device."""

import json

import pytest

from framework.crawler.pipeline import build_kit, run_kit
from tests.test_crawler import APP, FakeDriver


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def test_run_kit_writes_full_kit(tmp_path):
    config = {"package": APP, "targets": ["python_pytest"], "output": str(tmp_path)}
    summary = run_kit(config, driver=FakeDriver())

    assert summary["package"] == APP
    assert summary["screens"] >= 1
    assert summary["cases"] >= 1
    assert summary["targets"] == ["python_pytest"]
    assert (tmp_path / "inventory.md").exists()
    assert (tmp_path / "graph.mmd").exists()
    assert (tmp_path / "graph.json").exists()
    assert list((tmp_path / "python_pytest").glob("test_*.py"))
    # graph json is well-formed
    json.loads((tmp_path / "graph.json").read_text())


def test_multiple_targets(tmp_path):
    summary = run_kit(
        {"package": APP, "targets": ["python_pytest", "java_testng"], "output": str(tmp_path)},
        driver=FakeDriver(),
    )
    assert set(summary["targets"]) == {"python_pytest", "java_testng"}
    assert (tmp_path / "java_testng").exists()


def test_unknown_target_is_skipped(tmp_path):
    summary = run_kit(
        {"package": APP, "targets": ["python_pytest", "nope"], "output": str(tmp_path)},
        driver=FakeDriver(),
    )
    assert summary["targets"] == ["python_pytest"]


def test_scaffold_writes_runnable_project(tmp_path):
    pytest.importorskip("framework.codegen.scaffold")
    summary = run_kit(
        {"package": APP, "targets": ["js_webdriverio"], "output": str(tmp_path), "scaffold": True},
        driver=FakeDriver(),
    )
    assert summary["scaffolded"] == "js_webdriverio"
    assert (tmp_path / "package.json").exists()
    assert (tmp_path / "wdio.conf.js").exists()


def test_daemon_kit_generate_requires_package():
    from framework.cli.daemon_commands import JSONRPCServer

    with pytest.raises(ValueError):
        JSONRPCServer().handle_kit_generate({})
