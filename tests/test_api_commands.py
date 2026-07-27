"""`mobiscout api analyze` wires the previously-unreachable API-log analyzer
(framework/api_analyzer) to the CLI: parse a HAR capture, surface call patterns,
and generate test assertions. Drives it end-to-end over a small HAR fixture.
"""

import json

import pytest
from click.testing import CliRunner

from framework.api_analyzer.har import load_har_calls
from framework.cli.api_commands import api

_HAR = {
    "log": {
        "entries": [
            {
                "startedDateTime": "2026-07-24T10:00:00Z",
                "time": 42.0,
                "request": {"method": "GET", "url": "https://api.example.com/users", "headers": []},
                "response": {"status": 200, "headers": [], "content": {"text": "[]"}},
            },
            {
                "startedDateTime": "2026-07-24T10:00:01Z",
                "time": 88.0,
                "request": {
                    "method": "POST",
                    "url": "https://api.example.com/login",
                    "headers": [{"name": "Content-Type", "value": "application/json"}],
                    "postData": {"text": '{"u":"a"}'},
                },
                "response": {"status": 401, "headers": [], "content": {"text": "unauthorized"}},
            },
            {
                # A method we do not model — must be skipped, not crash.
                "startedDateTime": "2026-07-24T10:00:02Z",
                "request": {"method": "TRACE", "url": "https://api.example.com/x", "headers": []},
                "response": {"status": 200, "headers": []},
            },
        ]
    }
}


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def har_file(tmp_path):
    p = tmp_path / "capture.har"
    p.write_text(json.dumps(_HAR), encoding="utf-8")
    return p


def test_load_har_calls_parses_and_skips_unmodelled_methods(har_file):
    calls = load_har_calls(har_file)
    assert [c.method.value for c in calls] == ["GET", "POST"]  # TRACE skipped
    login = calls[1]
    assert login.url.endswith("/login")
    assert login.response_status == 401
    assert login.request_body == '{"u":"a"}'
    assert login.duration_ms == 88.0


def test_api_analyze_command_runs(runner, har_file):
    result = runner.invoke(api, ["analyze", str(har_file)])
    assert result.exit_code == 0, result.output
    assert "API call" in result.output


def test_api_analyze_writes_reports(runner, har_file, tmp_path):
    out = tmp_path / "reports"
    result = runner.invoke(api, ["analyze", str(har_file), "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "api_calls.har").exists()
    assertions = json.loads((out / "assertions.json").read_text(encoding="utf-8"))
    assert isinstance(assertions, list)


def test_api_analyze_empty_har_aborts(runner, tmp_path):
    empty = tmp_path / "empty.har"
    empty.write_text(json.dumps({"log": {"entries": []}}), encoding="utf-8")
    result = runner.invoke(api, ["analyze", str(empty)])
    assert result.exit_code != 0
