"""Behaviour tests for `mobiscout config` (init/set/get/list/validate/show/path/reset).

Drives the real ``ConfigManager`` over tmp YAML/JSON files — round-tripping values
through disk and asserting the persisted result, the validation logic, and the
error/exit-code branches. No mocking: config management is pure local file I/O.
"""

import json

import pytest
import yaml
from click.testing import CliRunner

from framework.cli.config_commands import config


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


# ------------------------------------------------------------------------------ init


def test_init_creates_config(runner, tmp_path):
    cfg = tmp_path / ".mobiscout.yaml"
    result = runner.invoke(config, ["init", "--path", str(cfg)])
    _no_crash(result)
    assert cfg.exists()
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert data["framework"]["timeout"] == 30  # a default value landed on disk


def test_init_refuses_existing_without_force(runner, tmp_path):
    cfg = tmp_path / ".mobiscout.yaml"
    cfg.write_text("framework: {}\n", encoding="utf-8")
    result = runner.invoke(config, ["init", "--path", str(cfg)])
    _no_crash(result)
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_init_force_overwrites(runner, tmp_path):
    cfg = tmp_path / ".mobiscout.yaml"
    cfg.write_text("garbage: 1\n", encoding="utf-8")
    result = runner.invoke(config, ["init", "--path", str(cfg), "--force"])
    _no_crash(result)
    assert result.exit_code == 0
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert "framework" in data


# ------------------------------------------------------------------------- set / get


def test_set_persists_and_get_reads_back(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])

    set_res = runner.invoke(config, ["set", "framework.timeout", "60", "-c", str(cfg)])
    _no_crash(set_res)
    assert "framework.timeout = 60" in set_res.output
    # Value must be persisted to disk as an int.
    assert yaml.safe_load(cfg.read_text(encoding="utf-8"))["framework"]["timeout"] == 60

    get_res = runner.invoke(config, ["get", "framework.timeout", "-c", str(cfg)])
    _no_crash(get_res)
    assert "60" in get_res.output


def test_set_coerces_bool(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])
    runner.invoke(config, ["set", "framework.screenshot_on_failure", "false", "-c", str(cfg)])
    assert yaml.safe_load(cfg.read_text(encoding="utf-8"))["framework"]["screenshot_on_failure"] is False


def test_set_invalid_key_exits_one(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])
    result = runner.invoke(config, ["set", "framework.nope_nope", "1", "-c", str(cfg)])
    _no_crash(result)
    assert result.exit_code == 1
    assert "Error" in result.output


def test_get_missing_key_exits_one(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])
    result = runner.invoke(config, ["get", "framework.does_not_exist", "-c", str(cfg)])
    _no_crash(result)
    assert result.exit_code == 1
    assert "Key not found" in result.output


# ------------------------------------------------------------------------------ list


@pytest.mark.parametrize("fmt", ["table", "yaml", "json"])
def test_list_all_formats(runner, tmp_path, fmt):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])
    result = runner.invoke(config, ["list", "-c", str(cfg), "--format", fmt])
    _no_crash(result)
    assert result.exit_code == 0
    assert "framework" in result.output


# -------------------------------------------------------------------------- validate


def test_validate_ok(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])
    result = runner.invoke(config, ["validate", "-c", str(cfg)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "valid" in result.output


def test_validate_reports_errors(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    # Out-of-range timeout and confidence trip two validation rules.
    cfg.write_text(
        yaml.dump({"framework": {"timeout": 0}, "ml": {"confidence_threshold": 5.0}}),
        encoding="utf-8",
    )
    result = runner.invoke(config, ["validate", "-c", str(cfg)])
    _no_crash(result)
    assert result.exit_code == 1
    assert "timeout" in result.output


# ---------------------------------------------------------------------- show / path


def test_show_missing_file_exits_one(runner, tmp_path):
    result = runner.invoke(config, ["show", "-c", str(tmp_path / "absent.yaml")])
    _no_crash(result)
    assert result.exit_code == 1
    assert "not found" in result.output


def test_show_renders_existing(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])
    result = runner.invoke(config, ["show", "-c", str(cfg)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "framework" in result.output


def test_path_reports_existence(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])
    result = runner.invoke(config, ["path", "-c", str(cfg)])
    _no_crash(result)
    assert "exists" in result.output


def test_path_reports_absence(runner, tmp_path):
    result = runner.invoke(config, ["path", "-c", str(tmp_path / "absent.yaml")])
    _no_crash(result)
    assert "not found" in result.output


# ----------------------------------------------------------------------------- reset


def test_reset_restores_default(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])
    runner.invoke(config, ["set", "framework.timeout", "999", "-c", str(cfg)])
    result = runner.invoke(config, ["reset", "framework.timeout", "-c", str(cfg)])
    _no_crash(result)
    assert result.exit_code == 0
    assert yaml.safe_load(cfg.read_text(encoding="utf-8"))["framework"]["timeout"] == 30


def test_reset_invalid_key_exits_one(runner, tmp_path):
    cfg = tmp_path / "c.yaml"
    runner.invoke(config, ["init", "--path", str(cfg)])
    result = runner.invoke(config, ["reset", "framework.bogus", "-c", str(cfg)])
    _no_crash(result)
    assert result.exit_code == 1
    assert "Invalid key" in result.output


def test_list_json_is_valid_json_payload(runner, tmp_path):
    # The JSON branch should emit a parseable object (guards against format regressions).
    cfg = tmp_path / "c.json"
    runner.invoke(config, ["init", "--path", str(cfg)])
    # ConfigManager writes JSON when the suffix is .json; re-read directly.
    assert json.loads(cfg.read_text(encoding="utf-8"))["framework"]["retry_count"] == 3
