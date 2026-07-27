"""Behavior tests for the `mock` CLI group (API mock record/replay tooling).

The commands construct an APIMocker with the default ``mock_data`` directory
(relative to cwd), so each test runs inside a chdir'd tmp_path to keep real
session files isolated. The proxy-serving `record`/`replay` commands need a live
network endpoint and Ctrl+C, so they are out of scope here; everything else
(swagger import, list, inspect, export/import roundtrip, delete, url rewrite) is
driven against real on-disk sessions.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.mock_commands import mock


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _in_tmp_cwd(tmp_path, monkeypatch):
    # Sessions persist under ./mock_data — isolate them per test.
    monkeypatch.chdir(tmp_path)


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


_SWAGGER = {
    "openapi": "3.0.0",
    "info": {"title": "Demo", "version": "1.0"},
    "paths": {
        "/users": {"get": {"responses": {"200": {"description": "ok"}}}},
        "/users/{id}": {"get": {"responses": {"200": {"description": "ok"}}}},
    },
}


def _swagger_file(tmp_path: Path) -> Path:
    path = tmp_path / "api.json"
    path.write_text(json.dumps(_SWAGGER), encoding="utf-8")
    return path


def test_list_empty(runner):
    result = runner.invoke(mock, ["list"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No mock sessions found" in result.output


def test_from_swagger_generates_and_lists(runner, tmp_path):
    result = runner.invoke(mock, ["from-swagger", str(_swagger_file(tmp_path)), "demo"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Generated" in result.output
    # The generated session is now discoverable via list.
    listed = runner.invoke(mock, ["list"])
    assert "demo" in listed.output


def test_from_swagger_missing_file(runner, tmp_path):
    result = runner.invoke(mock, ["from-swagger", str(tmp_path / "nope.json"), "demo"])
    _no_crash(result)
    assert "File not found" in result.output


def test_inspect_existing_session(runner, tmp_path):
    runner.invoke(mock, ["from-swagger", str(_swagger_file(tmp_path)), "demo"])
    result = runner.invoke(mock, ["inspect", "demo"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Total mocks" in result.output


def test_inspect_missing_session(runner):
    result = runner.invoke(mock, ["inspect", "ghost"])
    _no_crash(result)
    assert "not found" in result.output


def test_export_import_roundtrip(runner, tmp_path):
    runner.invoke(mock, ["from-swagger", str(_swagger_file(tmp_path)), "demo"])
    exported = tmp_path / "demo.export.json"
    result = runner.invoke(mock, ["export", "demo", "-o", str(exported)])
    _no_crash(result)
    assert exported.exists()

    imported = runner.invoke(mock, ["import", str(exported)])
    _no_crash(imported)
    assert "Imported session" in imported.output


def test_export_missing_session(runner, tmp_path):
    result = runner.invoke(mock, ["export", "ghost", "-o", str(tmp_path / "x.json")])
    _no_crash(result)
    assert "not found" in result.output


def test_delete_with_confirmation(runner, tmp_path):
    runner.invoke(mock, ["from-swagger", str(_swagger_file(tmp_path)), "demo"])
    result = runner.invoke(mock, ["delete", "demo"], input="y\n")
    _no_crash(result)
    assert "Deleted session" in result.output
    listed = runner.invoke(mock, ["list"])
    assert "demo" not in listed.output


def test_rewrite_urls(runner, tmp_path):
    runner.invoke(mock, ["from-swagger", str(_swagger_file(tmp_path)), "demo"])
    result = runner.invoke(mock, ["rewrite-urls", "demo", "https://api.example.com", "https://staging.example.com"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Rewrote" in result.output


def test_rewrite_urls_missing_session(runner):
    result = runner.invoke(mock, ["rewrite-urls", "ghost", "http://a", "http://b"])
    _no_crash(result)
    assert "not found" in result.output
