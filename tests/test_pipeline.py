"""Parameterized pipeline: config in, artifact kit out. Driven with the fake
crawler driver so the whole crawl→kit path runs without a device."""

import json

import pytest

import framework.crawler.pipeline as pipeline
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
    json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))


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


# --- open-core entitlement enforcement (the seam a paid tier limits) -----------
# FakeDriver yields 4 screens / 7 cases unlimited; a limited provider must cap the
# kit. These prove cap_screens/cap_tests are actually wired into build_kit, not
# just defined — the free-tier quota the PRO layer sells against.


@pytest.fixture()
def _limited(monkeypatch):
    """Install a limited entitlements provider for the duration of one test."""
    from framework.licensing import Entitlements, Tier, reset_provider, set_provider

    def _install(*, max_screens=None, max_tests=None):
        set_provider(lambda: Entitlements(tier=Tier.FREE, max_screens=max_screens, max_tests=max_tests))

    yield _install
    reset_provider()


def test_screen_cap_trims_kit_and_keeps_transitions_consistent(_limited, tmp_path):
    _limited(max_screens=2)
    summary = run_kit({"package": APP, "targets": ["python_pytest"], "output": str(tmp_path)}, driver=FakeDriver())
    assert summary["screens"] == 2  # capped from the unlimited 4
    # Every transition still references a kept screen — no dangling endpoints.
    graph = json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in graph.get("nodes", [])}
    for edge in graph.get("edges", []):
        assert edge["src"] in node_ids and edge["dst"] in node_ids


def test_test_cap_trims_generated_cases(_limited, tmp_path):
    _limited(max_tests=2)
    summary = run_kit({"package": APP, "targets": ["python_pytest"], "output": str(tmp_path)}, driver=FakeDriver())
    assert summary["cases"] == 2  # capped from the unlimited 7
    assert summary["screens"] == 4  # screens untouched by the test cap


def test_unlimited_default_caps_nothing(tmp_path):
    from framework.licensing import reset_provider

    reset_provider()  # the open-core default is UNLIMITED
    summary = run_kit({"package": APP, "targets": ["python_pytest"], "output": str(tmp_path)}, driver=FakeDriver())
    assert summary["screens"] == 4 and summary["cases"] == 7


# --- crawl + captured traffic (HAR) -> UI tests AND API tests in one kit --------

_HAR = {
    "log": {
        "entries": [
            {"request": {"method": "GET", "url": "https://api.bank.com/accounts"}, "response": {"status": 200}},
            {"request": {"method": "POST", "url": "https://api.bank.com/transfers"}, "response": {"status": 201}},
        ]
    }
}


def _write_har(tmp_path):
    import json

    p = tmp_path / "capture.har"
    p.write_text(json.dumps(_HAR), encoding="utf-8")
    return str(p)


def test_run_kit_with_har_also_emits_api_tests(tmp_path):
    """build_kit path: a crawl given a proxy HAR emits test_api.py alongside the UI tests."""
    summary = run_kit(
        {"package": APP, "targets": ["python_pytest"], "output": str(tmp_path), "har": _write_har(tmp_path)},
        driver=FakeDriver(),
    )
    assert summary["api_tests"] == 2  # both captured endpoints
    assert (tmp_path / "test_api.py").exists()
    assert summary["cases"] >= 1  # UI tests still produced


def test_write_kit_with_har_emits_api_tests(tmp_path):
    """crawl-CLI path (write_kit): the same HAR wiring produces API tests."""
    from framework.cli.crawl_service import write_kit
    from framework.crawler.app_crawler import CrawlResult

    report = write_kit(
        result=CrawlResult(),
        output=str(tmp_path),
        package=APP,
        targets="python_pytest",
        style="flat",
        scaffold=False,
        server="http://localhost:4723",
        app_activity=None,
        launch_args=(),
        har=_write_har(tmp_path),
    )
    assert (tmp_path / "test_api.py").exists()
    assert any("API tests from captured traffic" in line for line in report.info)


def test_run_kit_collects_ios_crash_into_kit(tmp_path, monkeypatch):
    """A crash during the crawl is captured as a first-class kit artifact: the
    matching .ips lands in crashes/ and the summary counts it."""
    home = tmp_path / "home"
    reports = home / "Library" / "Logs" / "DiagnosticReports"
    reports.mkdir(parents=True)
    (reports / "ChaosBank-2026-08-08-000000.ips").write_text('{"crash": 1}')
    monkeypatch.setattr(pipeline.Path, "home", staticmethod(lambda: home))

    out = tmp_path / "kit"
    summary = run_kit(
        {"package": "com.acme.ChaosBank", "platform": "ios", "targets": ["python_pytest"], "output": str(out)},
        driver=FakeDriver(),
    )
    assert summary["crashes"] == 1
    assert (out / "crashes" / "ChaosBank-2026-08-08-000000.ips").is_file()


def test_run_kit_reports_zero_crashes_when_none(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline.Path, "home", staticmethod(lambda: tmp_path / "empty"))
    out = tmp_path / "kit"
    summary = run_kit(
        {"package": "com.acme.NoCrash", "platform": "ios", "targets": ["python_pytest"], "output": str(out)},
        driver=FakeDriver(),
    )
    assert summary["crashes"] == 0
    assert not (out / "crashes").exists()


def test_android_crash_needs_a_serial():
    # No device serial -> nothing to query, no crash (and never raises).
    assert pipeline._collect_crashes({"platform": "android", "package": "com.x.App"}, 0.0) == []


def test_android_crash_collected_from_logcat_buffer(monkeypatch):
    """Android crashes come from logcat's crash buffer: a fatal exception for the
    app is aggregated into one <package>-logcat-crash.txt artifact."""
    import subprocess
    from types import SimpleNamespace

    logcat = "08-08 21:00:00.000 E/AndroidRuntime: FATAL EXCEPTION: main\n  com.acme.app crashed\n"

    def fake_run(cmd, **kw):
        assert cmd[:3] == ["adb", "-s", "emulator-5554"]
        assert "-b" in cmd and "crash" in cmd
        return SimpleNamespace(stdout=logcat, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    got = pipeline._collect_crashes(
        {"platform": "android", "package": "com.acme.app", "udid": "emulator-5554"}, 0.0
    )
    assert len(got) == 1
    name, data = got[0]
    assert name == "com.acme.app-logcat-crash.txt"
    assert b"FATAL EXCEPTION" in data


def test_android_no_crash_when_buffer_clean(monkeypatch):
    import subprocess
    from types import SimpleNamespace

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: SimpleNamespace(stdout="", returncode=0))
    assert pipeline._collect_crashes({"platform": "android", "package": "com.x.App", "udid": "s1"}, 0.0) == []
