"""Behavior tests for the `business` CLI group.

`analyze` and `complexity` run the real analyzers over a tmp source tree; the
display/generation subcommands (`scenarios`, `features`, `testdata`, `edgecases`,
`statemachines`, `negative`, `contracts`) are driven from a hand-built analysis
file so their formatting + file-writing branches execute deterministically
without needing a large sample project.
"""

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from framework.cli.business_logic_commands import business


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _source_tree(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "checkout.py").write_text(
        "def checkout(cart, coupon=None):\n"
        "    total = 0\n"
        "    for item in cart:\n"
        "        total += item\n"
        "    if coupon:\n"
        "        total *= 0.9\n"
        "    if total < 0:\n"
        "        raise ValueError('negative')\n"
        "    return total\n",
        encoding="utf-8",
    )
    return src


def _analysis_file(tmp_path: Path) -> Path:
    data = {
        "user_flows": [
            {
                "name": "Login",
                "description": "Login flow",
                "steps": ["open", "enter", "submit"],
                "entry_point": "LoginScreen",
                "success_outcome": "home",
                "failure_outcomes": ["error"],
                "source_files": ["login.kt"],
            }
        ],
        "mock_data": {
            "User": {"count": 5, "start_id": 1, "end_id": 5, "source": "db.json"},
            "Product": {"count": 3, "type": "Product", "source": "seed.json"},
        },
        "edge_cases": [
            {"type": "boundary", "description": "empty username", "severity": "high", "test_data": [""]},
        ],
        "state_machines": [
            {
                "name": "Auth",
                "states": ["idle", "loading", "done"],
                "initial_state": "idle",
                "transitions": {"idle": ["loading"], "loading": ["done"]},
            }
        ],
        "negative_test_cases": [
            {"name": "wrong password", "expected_outcome": "reject", "priority": "high"},
            {"name": "empty form", "expected_outcome": "validation error", "priority": "medium"},
        ],
        "api_contracts": [
            {"method": "POST", "endpoint": "/login", "description": "auth", "source_file": "api.kt"},
        ],
    }
    path = tmp_path / "bl.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("fmt", ["yaml", "json"])
def test_analyze_writes_and_summarizes(runner, tmp_path, fmt):
    out = tmp_path / f"out.{fmt}"
    result = runner.invoke(
        business,
        ["analyze", "--source", str(_source_tree(tmp_path)), "--output", str(out), "--format", fmt],
    )
    _no_crash(result)
    assert result.exit_code == 0
    assert "Analysis Summary" in result.output
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    parsed = json.loads(text) if fmt == "json" else yaml.safe_load(text)
    assert isinstance(parsed, dict)


def test_scenarios_generates_file(runner, tmp_path):
    out = tmp_path / "scenarios.yaml"
    result = runner.invoke(business, ["scenarios", "--input", str(_analysis_file(tmp_path)), "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert "scenarios" in loaded


def test_features_writes_feature_file(runner, tmp_path):
    out = tmp_path / "features" / "bl.feature"
    result = runner.invoke(business, ["features", "--input", str(_analysis_file(tmp_path)), "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    # parent dir is created and a gherkin feature is written.
    assert out.exists()
    assert out.read_text(encoding="utf-8").strip()


def test_testdata_shows_entities(runner, tmp_path):
    result = runner.invoke(business, ["testdata", "--input", str(_analysis_file(tmp_path))])
    _no_crash(result)
    assert result.exit_code == 0
    assert "User" in result.output
    assert "Product" in result.output


def test_edgecases_groups_by_type(runner, tmp_path):
    result = runner.invoke(business, ["edgecases", "--input", str(_analysis_file(tmp_path))])
    _no_crash(result)
    assert result.exit_code == 0
    assert "BOUNDARY" in result.output


def test_statemachines_lists_states(runner, tmp_path):
    result = runner.invoke(business, ["statemachines", "--input", str(_analysis_file(tmp_path))])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Auth" in result.output
    assert "idle" in result.output


def test_negative_writes_and_groups(runner, tmp_path):
    out = tmp_path / "neg.yaml"
    result = runner.invoke(business, ["negative", "--input", str(_analysis_file(tmp_path)), "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "HIGH Priority" in result.output
    assert out.exists()
    assert "negative_test_cases" in yaml.safe_load(out.read_text(encoding="utf-8"))


def test_contracts_lists_endpoints(runner, tmp_path):
    result = runner.invoke(business, ["contracts", "--input", str(_analysis_file(tmp_path))])
    _no_crash(result)
    assert result.exit_code == 0
    assert "POST /login" in result.output


def test_testdata_empty_when_no_mock_data(runner, tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text(yaml.dump({"user_flows": []}), encoding="utf-8")
    result = runner.invoke(business, ["testdata", "--input", str(path)])
    _no_crash(result)
    assert "No mock data found" in result.output


def test_complexity_analyzes_python(runner, tmp_path):
    out = tmp_path / "cc.yaml"
    result = runner.invoke(business, ["complexity", "--source", str(_source_tree(tmp_path)), "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Complexity Summary" in result.output
    assert out.exists()
