"""Behaviour tests for the `mobiscout fuzz` CLI group (framework/cli/fuzz_commands.py).

These drive each subcommand end-to-end through CliRunner and assert on the real
side effects: the JSON files written to disk, the statistics rendered, and the
"SIMULATED" honesty banner shown when UI fuzzing runs with no device driver.
The only thing mocked is `requests.request` (real network I/O the API fuzzer
would otherwise attempt) — everything else is the framework's own logic.
"""

import json
from types import SimpleNamespace

import pytest
import requests
from click.testing import CliRunner

from framework.cli.fuzz_commands import fuzz


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    """A command may exit non-zero but must never raise an unexpected exception."""
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def test_generate_writes_json_file(runner, tmp_path):
    out = tmp_path / "inputs.json"
    result = runner.invoke(fuzz, ["generate", "--type", "email", "--count", "5", "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()

    data = json.loads(out.read_text())
    assert isinstance(data, list) and len(data) == 5
    # Every serialized input carries the fields the command promises.
    for entry in data:
        assert entry["type"] == "email"
        assert "value" in entry and "strategy" in entry


def test_generate_default_no_output(runner):
    result = runner.invoke(fuzz, ["generate", "--type", "text", "--count", "3"])
    _no_crash(result)
    assert result.exit_code == 0
    # The panel header echoes the requested type/count.
    assert "TEXT" in result.output


def test_mutate_produces_requested_count(runner):
    result = runner.invoke(fuzz, ["mutate", "test@example.com", "--mutations", "7"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "7 Mutations" in result.output


def test_ui_fuzz_is_flagged_simulated_and_saves_results(runner, tmp_path):
    # With no device driver attached, UI fuzzing must NOT invent findings — it
    # generates inputs and honestly labels the run as SIMULATED.
    out = tmp_path / "ui.json"
    result = runner.invoke(fuzz, ["ui", "username_field", "-t", "text", "-n", "5", "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "SIMULATED" in result.output

    saved = json.loads(out.read_text())
    assert saved["target"] == "username_field"
    assert saved["statistics"]["total_inputs"] == 5
    # Simulated run => no fabricated crashes.
    assert saved["statistics"]["crashes"] == 0


def test_api_fuzz_reports_stats(runner, tmp_path, monkeypatch):
    # Mock the HTTP layer: a healthy endpoint always answers 200.
    monkeypatch.setattr(requests, "request", lambda *a, **k: SimpleNamespace(status_code=200))

    out = tmp_path / "api.json"
    result = runner.invoke(
        fuzz, ["api", "http://svc.test/login", "-m", "POST", "-t", "text", "-n", "5", "-o", str(out)]
    )
    _no_crash(result)
    assert result.exit_code == 0

    saved = json.loads(out.read_text())
    assert saved["total_requests"] == 5
    assert saved["errors"] == 0
    assert saved["crashes"] == 0


def test_api_fuzz_flags_server_errors_as_crashes(runner, monkeypatch):
    # A 5xx on a fuzz input is a genuine crash finding.
    monkeypatch.setattr(requests, "request", lambda *a, **k: SimpleNamespace(status_code=500))

    result = runner.invoke(fuzz, ["api", "http://svc.test/boom", "-m", "GET", "-t", "text", "-n", "5"])
    _no_crash(result)
    assert result.exit_code == 0
    # 500s counted as crashes drive the vulnerable-endpoint panel.
    assert "Vulnerable Endpoint" in result.output


def test_campaign_from_config_writes_report(runner, tmp_path):
    config = tmp_path / "cfg.json"
    config.write_text(
        json.dumps(
            {
                "ui_targets": [{"id": "field1", "type": "text_field", "input_type": "text"}],
                "api_endpoints": [],
            }
        )
    )
    out = tmp_path / "report.json"
    result = runner.invoke(fuzz, ["campaign", "--config", str(config), "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()

    report = json.loads(out.read_text())
    assert "ui" in report
    assert report["ui"]["total_inputs"] == 50  # one text_field target * 50 inputs


def test_campaign_default_targets(runner, tmp_path, monkeypatch):
    # Default demo targets include API endpoints; keep it offline & fast.
    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(requests, "request", _boom)

    out = tmp_path / "default_report.json"
    result = runner.invoke(fuzz, ["campaign", "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()
    report = json.loads(out.read_text())
    assert "ui" in report and "api" in report


def test_list_strategies(runner):
    result = runner.invoke(fuzz, ["list"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Mutation" in result.output
    assert "Boundary" in result.output


def test_analyze_report(runner, tmp_path):
    report = tmp_path / "results.json"
    report.write_text(
        json.dumps(
            {
                "ui": {
                    "statistics": {"crash_rate": 0.10},
                    "targets": [{"id": "login_btn", "crashes": 2, "inputs": 50}],
                },
                "api": {
                    "vulnerable_endpoints": [{"endpoint": "/api/login", "error_rate": 0.5}],
                },
            }
        )
    )
    result = runner.invoke(fuzz, ["analyze", str(report)])
    _no_crash(result)
    assert result.exit_code == 0
    # High crash rate + a vulnerable endpoint should both surface.
    assert "crash rate" in result.output
    assert "vulnerable endpoint" in result.output.lower()
    assert "login_btn" in result.output


def test_analyze_missing_file_errors(runner, tmp_path):
    result = runner.invoke(fuzz, ["analyze", str(tmp_path / "nope.json")])
    _no_crash(result)
    assert result.exit_code != 0  # click.Path(exists=True) rejects it
