"""The comprehensive security scan lives in a service layer so its orchestration
— which analyses run, severity tallying, runtime scoring, report saving, exit
code — is testable with stub analyzers instead of real app binaries."""

import json
from types import SimpleNamespace

import pytest

from framework.cli.security import comprehensive_service as svc
from framework.cli.security.comprehensive_service import run_comprehensive_scan, save_reports


def _sev(value):
    return SimpleNamespace(severity=SimpleNamespace(value=value))


def _protection(detected):
    return SimpleNamespace(detected=detected)


@pytest.fixture()
def stub_analyzers(monkeypatch, tmp_path):
    """Replace the five analyzer classes with deterministic stubs."""
    decompiled_dir = tmp_path / "decompiled"
    decompiled_dir.mkdir()

    decompile_result = SimpleNamespace(
        output_dir=str(decompiled_dir),
        security_findings=[1, 2, 3],
        to_dict=lambda: {"kind": "decompile"},
    )
    sast_result = SimpleNamespace(
        findings=[_sev("critical"), _sev("high"), _sev("low")],
        vulnerabilities=[1, 2],
        to_dict=lambda: {"kind": "sast"},
    )
    runtime_result = SimpleNamespace(
        root_detection=_protection(True),
        emulator_detection=_protection(True),
        debug_detection=_protection(False),
        tamper_detection=_protection(False),
        hook_detection=_protection(False),
        ssl_pinning=_protection(False),
        obfuscation=_protection(False),
        to_dict=lambda: {"kind": "runtime"},
    )
    supply_result = SimpleNamespace(
        vulnerabilities=[SimpleNamespace(severity="critical"), SimpleNamespace(severity="high")],
        to_dict=lambda: {"kind": "supply"},
    )
    dast_result = SimpleNamespace(
        findings=[_sev("high")],
        to_dict=lambda: {"kind": "dast"},
    )

    monkeypatch.setattr(svc, "Decompiler", lambda: SimpleNamespace(decompile=lambda *a, **k: decompile_result))
    monkeypatch.setattr(svc, "SASTAnalyzer", lambda: SimpleNamespace(analyze=lambda p: sast_result))
    monkeypatch.setattr(svc, "RuntimeProtectionAnalyzer", lambda: SimpleNamespace(analyze=lambda *a: runtime_result))
    monkeypatch.setattr(svc, "SupplyChainAnalyzer", lambda: SimpleNamespace(analyze=lambda p: supply_result))
    monkeypatch.setattr(svc, "DASTAnalyzer", lambda: SimpleNamespace(analyze=lambda h: dast_result))
    return tmp_path


def test_full_scan_tallies_severities_and_scores_runtime(stub_analyzers, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    steps = []
    scan = run_comprehensive_scan(
        tmp_path / "app.apk",
        "android",
        source_path=src,
        target_host="api.example.com",
        on_step=steps.append,
    )
    # SAST (1c/1h) + supply (1c/1h) + DAST (0c/1h) => 2 critical, 3 high.
    assert scan.total_critical == 2
    assert scan.total_high == 3
    # 2 of 7 protections detected.
    assert scan.runtime_score == pytest.approx(2 / 7 * 100)
    assert scan.exit_code == 2  # criticals present
    assert len(steps) == 5  # every step announced for the progress display
    assert [a[1] for a in scan.analyses] == ["Complete"] * 5


def test_scan_skips_optional_analyses_without_source_or_target(stub_analyzers, tmp_path):
    # No source_path and no target_host: supply chain and DAST are skipped; SAST
    # still runs against the decompiled output. Only SAST contributes (1c/1h).
    scan = run_comprehensive_scan(tmp_path / "app.apk", "android")
    assert scan.supply_result is None
    assert scan.dast_result is None
    statuses = {name: status for name, status, _ in scan.analyses}
    assert statuses["Supply Chain"] == "Skipped"
    assert statuses["DAST"] == "Skipped"
    assert statuses["SAST"] == "Complete"
    assert scan.total_critical == 1 and scan.total_high == 1
    assert scan.exit_code == 2


def test_exit_code_is_one_for_highs_only_and_zero_when_clean(stub_analyzers, tmp_path):
    scan = run_comprehensive_scan(tmp_path / "app.apk", "android")
    scan.total_critical = 0
    assert scan.exit_code == 1
    scan.total_high = 0
    assert scan.exit_code == 0


def test_save_reports_writes_only_the_analyses_that_ran(stub_analyzers, tmp_path):
    out = tmp_path / "reports"
    out.mkdir()
    scan = run_comprehensive_scan(tmp_path / "app.apk", "android")  # no supply/dast
    save_reports(scan, out, "MyApp", "android")

    assert (out / "MyApp_decompile.json").exists()
    assert (out / "MyApp_sast.json").exists()
    assert (out / "MyApp_runtime.json").exists()
    assert not (out / "MyApp_supply_chain.json").exists()
    assert not (out / "MyApp_dast.json").exists()

    summary = json.loads((out / "MyApp_summary.json").read_text())
    assert summary["app_name"] == "MyApp"
    assert "Supply Chain" not in summary["analyses_completed"]
    assert "SAST" in summary["analyses_completed"]
