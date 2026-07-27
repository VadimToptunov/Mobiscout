"""Behavior tests for the `observe` CLI group (metrics/logs/traces).

Drives the real ObservabilityManager singleton for metrics export (prometheus +
json, to stdout and to file) and status, plus the file-backed `logs` and `trace`
commands over tmp fixtures — including the missing-file branches (trace exits 1).
The `--follow` tail loop is an infinite blocking path and is intentionally not
exercised.
"""

import json

import pytest
from click.testing import CliRunner

from framework.cli.observability_commands import observe_


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def test_metrics_prometheus_to_stdout(runner):
    result = runner.invoke(observe_, ["metrics", "--format", "prometheus"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Prometheus Metrics" in result.output


def test_metrics_json_to_file(runner, tmp_path):
    out = tmp_path / "metrics.json"
    result = runner.invoke(observe_, ["metrics", "--format", "json", "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_status(runner):
    result = runner.invoke(observe_, ["status"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Observability Status" in result.output
    assert "Metrics" in result.output


def test_logs_missing_file(runner, tmp_path):
    result = runner.invoke(observe_, ["logs", "-f", str(tmp_path / "absent.json")])
    _no_crash(result)
    assert "not found" in result.output


def test_logs_displays_entries(runner, tmp_path):
    log = tmp_path / "app.json"
    log.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-07-27T10:00:00.123", "level": "INFO", "message": "started"}),
                json.dumps({"timestamp": "2026-07-27T10:00:01.000", "level": "ERROR", "message": "boom"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(observe_, ["logs", "-f", str(log)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Structured Logs" in result.output


def test_logs_level_filter(runner, tmp_path):
    log = tmp_path / "app.json"
    log.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-07-27T10:00:00", "level": "INFO", "message": "info-msg"}),
                json.dumps({"timestamp": "2026-07-27T10:00:01", "level": "ERROR", "message": "error-msg"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(observe_, ["logs", "-f", str(log), "--level", "ERROR"])
    _no_crash(result)
    assert result.exit_code == 0
    # Only the ERROR entry passes the filter.
    assert "error-msg" in result.output
    assert "info-msg" not in result.output


def test_trace_analyzes_spans(runner, tmp_path):
    trace = tmp_path / "trace.json"
    trace.write_text(
        json.dumps(
            {
                "trace_id": "abc123",
                "spans": [
                    {"name": "db.query", "duration_ms": 12.5, "attributes": {"table": "users"}},
                    {"name": "http.get", "duration_ms": 7.0, "attributes": {}},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(observe_, ["trace", str(trace)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "abc123" in result.output
    assert "Total Spans:" in result.output


def test_trace_missing_file_exits_one(runner, tmp_path):
    result = runner.invoke(observe_, ["trace", str(tmp_path / "gone.json")])
    _no_crash(result)
    assert result.exit_code == 1
    assert "not found" in result.output
