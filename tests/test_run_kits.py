"""Multi-app generation (device-free): run_kits builds a kit per config so a project's
Android + iOS apps generate in one action. run_kit is patched — we test the orchestration
(aggregation, error isolation, parallel/sequential dispatch), not a real crawl."""

import framework.crawler.pipeline as pipeline
from framework.crawler.pipeline import run_kits


def _fake_run_kit(config):
    # echo the package so the aggregation is checkable
    return {"package": config["package"], "screens": 3, "cases": 5}


def test_empty_configs_is_empty():
    assert run_kits([]) == []


def test_one_kit_per_config_aggregated(monkeypatch):
    monkeypatch.setattr(pipeline, "run_kit", _fake_run_kit)
    results = run_kits([{"package": "com.a"}, {"package": "com.b"}], parallel=False)
    assert [r["package"] for r in results] == ["com.a", "com.b"]
    assert all(r["screens"] == 3 for r in results)


def test_one_failure_does_not_sink_the_batch(monkeypatch):
    def flaky(config):
        if config["package"] == "com.bad":
            raise RuntimeError("device offline")
        return _fake_run_kit(config)

    monkeypatch.setattr(pipeline, "run_kit", flaky)
    results = run_kits([{"package": "com.good"}, {"package": "com.bad"}], parallel=False)
    assert results[0] == {"package": "com.good", "screens": 3, "cases": 5}
    assert results[1]["package"] == "com.bad" and "device offline" in results[1]["error"]
    assert results[1]["screens"] == 0


def test_parallel_runs_all_configs(monkeypatch):
    monkeypatch.setattr(pipeline, "run_kit", _fake_run_kit)
    configs = [{"package": f"com.app{i}"} for i in range(5)]
    results = run_kits(configs, parallel=True)
    assert {r["package"] for r in results} == {c["package"] for c in configs}


def test_daemon_rpc_generate_many(monkeypatch):
    from framework.cli.daemon_commands import JSONRPCServer

    monkeypatch.setattr(pipeline, "run_kit", _fake_run_kit)
    out = JSONRPCServer().handle_kit_generate_many(
        {"configs": [{"package": "com.a"}, {"package": "com.b"}], "parallel": False}
    )
    assert [r["package"] for r in out["results"]] == ["com.a", "com.b"]


def test_daemon_rpc_requires_configs_and_package():
    import pytest

    from framework.cli.daemon_commands import JSONRPCServer

    srv = JSONRPCServer()
    with pytest.raises(ValueError):
        srv.handle_kit_generate_many({"configs": []})
    with pytest.raises(ValueError):
        srv.handle_kit_generate_many({"configs": [{"platform": "android"}]})  # no package
