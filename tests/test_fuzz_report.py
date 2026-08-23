"""The shareable fuzzing-campaign report (fuzzer #3): renders findings, and is honest that
a simulated run (no device/endpoint) has no findings rather than implying crashes."""

from framework.fuzzing.fuzzer import FuzzingCampaign
from framework.fuzzing.report import fuzz_report


def test_simulated_run_reports_no_findings():
    md = fuzz_report({"ui": {"total_inputs": 50, "crashes": 0, "simulated": True, "targets": []}})
    assert "Simulated run" in md and "no findings" in md.lower()


def test_real_findings_render_a_table():
    results = {
        "ui": {
            "total_inputs": 10,
            "crashes": 2,
            "simulated": False,
            "findings": [{"target": "email", "strategy": "sql_injection", "value": "' OR 1=1", "crash": True}],
        }
    }
    md = fuzz_report(results)
    assert "### Findings" in md and "sql_injection" in md and "crash" in md


def test_clean_real_run_says_ok():
    md = fuzz_report({"api": {"total_requests": 10, "errors": 0, "simulated": False}})
    assert "✅" in md


def test_empty_campaign():
    assert "No campaign" in fuzz_report({})


def test_campaign_ui_run_without_a_device_is_flagged_simulated():
    camp = FuzzingCampaign()
    camp.run_ui_campaign([{"id": "email", "type": "text_field", "input_type": "text"}])
    ui = camp.campaign_results["ui"]
    assert ui["simulated"] is True
    assert not ui.get("findings")  # a simulated run yields no real findings
    assert "Simulated run" in camp.report_markdown()
