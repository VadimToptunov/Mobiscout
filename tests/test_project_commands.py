"""Behavior tests for the `project` CLI group and its pure helpers.

Drives analyze -> integrate -> generate over real tmp source trees (no devices,
no network), asserting the files each phase writes and the error branches. The
two module-level helpers (`transform_analysis_to_integration_format` and
`_find_app_model`) are unit-tested directly since they hold the load-bearing
data-shaping logic.
"""

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from framework.cli import project_commands
from framework.cli.project_commands import (
    project,
    _analyze_platform,
    _find_app_model,
    transform_analysis_to_integration_format,
)


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
    (src / "login.py").write_text(
        "def login(user, password):\n"
        "    if not user:\n"
        "        return False\n"
        "    if not password:\n"
        "        return False\n"
        "    return True\n",
        encoding="utf-8",
    )
    return src


@pytest.mark.parametrize("fmt", ["yaml", "json"])
def test_analyze_writes_result_file(runner, tmp_path, fmt):
    out = tmp_path / "analysis"
    result = runner.invoke(
        project,
        ["analyze", "--android-source", str(_source_tree(tmp_path)), "--output-dir", str(out), "--format", fmt],
    )
    _no_crash(result)
    assert result.exit_code == 0
    written = out / f"android_analysis.{fmt}"
    assert written.exists()
    # File is real, non-empty and parseable in its declared format.
    text = written.read_text(encoding="utf-8")
    parsed = json.loads(text) if fmt == "json" else yaml.safe_load(text)
    assert isinstance(parsed, dict)


def test_analyze_requires_a_source(runner, tmp_path):
    # validate_and_raise aborts when neither source option is given.
    result = runner.invoke(project, ["analyze", "--output-dir", str(tmp_path / "out")])
    _no_crash(result)
    assert result.exit_code != 0
    assert "source" in result.output.lower()


def test_integrate_creates_app_model(runner, tmp_path):
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    analysis = tmp_path / "an.yaml"
    analysis.write_text(
        yaml.dump(
            {
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
                "api_contracts": [{"method": "GET", "endpoint": "/session", "source_file": "s.kt"}],
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(project, ["integrate", "--analysis", str(analysis), "--project", str(proj)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Integration complete" in result.output
    # Integration persists an enriched app model that `generate` can later load.
    assert (proj / "config" / "app_model_enriched.yaml").exists()


def test_integrate_reports_invalid_json(runner, tmp_path):
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    bad = tmp_path / "broken.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")
    result = runner.invoke(project, ["integrate", "--analysis", str(bad), "--project", str(proj)])
    _no_crash(result)
    # Command handles the parse failure gracefully (prints error, returns 0).
    assert "Invalid file format" in result.output


def test_generate_errors_without_model(runner, tmp_path):
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    result = runner.invoke(project, ["generate", "--project", str(proj)])
    _no_crash(result)
    assert "No app model found" in result.output


def _project_with_model(tmp_path: Path) -> Path:
    """A project carrying a minimal but schema-valid app model."""
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    model = {
        "meta": {
            "schema_version": "1.0.0",
            "app_version": "1.0.0",
            "platform": "android",
            "recorded_at": "2025-01-01T00:00:00Z",
        },
        "screens": {"LoginScreen": {"name": "LoginScreen", "elements": [], "actions": []}},
        "api_calls": {},
        "flows": [],
    }
    (proj / "config" / "app_model.yaml").write_text(yaml.dump(model), encoding="utf-8")
    return proj


def test_generate_runs_over_valid_model(runner, tmp_path):
    proj = _project_with_model(tmp_path)
    result = runner.invoke(project, ["generate", "--project", str(proj)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Test Suite Generation Complete" in result.output


def test_generate_reports_invalid_model(runner, tmp_path):
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    # A model whose screens/api_calls are lists violates the AppModel schema;
    # generate must surface the load error gracefully rather than crash.
    (proj / "config" / "app_model.yaml").write_text(yaml.dump({"screens": [], "api_calls": []}), encoding="utf-8")
    result = runner.invoke(project, ["generate", "--project", str(proj)])
    _no_crash(result)
    assert "Error" in result.output


def test_fullcycle_end_to_end(runner, tmp_path):
    proj = tmp_path / "test-automation"
    result = runner.invoke(
        project,
        ["fullcycle", "--android-path", str(_source_tree(tmp_path)), "--project", str(proj)],
    )
    _no_crash(result)
    assert result.exit_code == 0
    assert "Full Cycle Complete" in result.output
    # Phase 1 wrote the analysis artifact into the project's output dir.
    assert (proj / "analysis" / "android_analysis.yaml").exists()


def test_fullcycle_requires_a_source(runner, tmp_path):
    result = runner.invoke(project, ["fullcycle", "--project", str(tmp_path / "p")])
    _no_crash(result)
    assert "At least one source" in result.output


def test_transform_maps_contracts_flows_and_screens():
    data = {
        "api_contracts": [{"method": "POST", "endpoint": "/log-in", "source_file": "api.kt"}],
        "user_flows": [
            {
                "name": "Login",
                "steps": ["a", "b"],
                "entry_point": "LoginScreen",
                "source_files": ["login.kt"],
            }
        ],
    }
    result = transform_analysis_to_integration_format(data)

    assert result["api_endpoints"][0]["method"] == "POST"
    assert result["api_endpoints"][0]["path"] == "/log-in"
    # Slashes and dashes become underscores for the generated function name.
    assert result["api_endpoints"][0]["function_name"] == "_log_in"
    assert result["navigation"][0]["name"] == "Login"
    # Entry point is promoted to a screen exactly once.
    assert result["screens"][0]["name"] == "LoginScreen"
    assert result["business_logic"] is data


def test_transform_deduplicates_screens():
    data = {
        "user_flows": [
            {"name": "A", "entry_point": "Home", "source_files": ["a"]},
            {"name": "B", "entry_point": "Home", "source_files": ["b"]},
        ]
    }
    result = transform_analysis_to_integration_format(data)
    assert [s["name"] for s in result["screens"]] == ["Home"]


def test_find_app_model_prefers_enriched(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "app_model.yaml").write_text("a: 1", encoding="utf-8")
    (config / "app_model_enriched.yaml").write_text("b: 2", encoding="utf-8")
    found = _find_app_model(tmp_path)
    assert found is not None and found.name == "app_model_enriched.yaml"


def test_find_app_model_glob_fallback(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "flykk_app_model_v2.yaml").write_text("x: 1", encoding="utf-8")
    found = _find_app_model(tmp_path)
    assert found is not None and found.name == "flykk_app_model_v2.yaml"


def test_find_app_model_returns_none_without_config(tmp_path):
    assert _find_app_model(tmp_path) is None


# --------------------------------------------------------------------------- #
# analyze — iOS platform, per-platform failure, and the no-results aggregation
# --------------------------------------------------------------------------- #


def _swift_source(tmp_path: Path) -> Path:
    src = tmp_path / "ios"
    src.mkdir()
    (src / "LoginView.swift").write_text(
        "import SwiftUI\nstruct LoginView {\n    func submit() { }\n    if count > 5 { }\n}\n",
        encoding="utf-8",
    )
    return src


def test_analyze_ios_source(runner, tmp_path):
    out = tmp_path / "analysis"
    result = runner.invoke(project, ["analyze", "--ios-source", str(_swift_source(tmp_path)), "--output-dir", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    # The iOS branch of `analyze` ran and wrote its own artifact.
    assert (out / "ios_analysis.yaml").exists()


def test_analyze_platform_returns_none_when_output_unwritable(tmp_path):
    # _analyze_platform swallows failures and returns None; make the output dir a
    # regular file so writing the result raises inside the analyzer's try block.
    src = _source_tree(tmp_path)
    not_a_dir = tmp_path / "afile"
    not_a_dir.write_text("x", encoding="utf-8")
    assert _analyze_platform("Android", src, not_a_dir, "yaml") is None


def test_analyze_reports_no_results(runner, tmp_path, monkeypatch):
    # When every per-platform analysis fails (returns None), the command reports
    # the aggregate failure rather than success.
    monkeypatch.setattr(project_commands, "_analyze_platform", lambda *a, **k: None)
    out = tmp_path / "analysis"
    result = runner.invoke(
        project, ["analyze", "--android-source", str(_source_tree(tmp_path)), "--output-dir", str(out)]
    )
    _no_crash(result)
    assert "Analysis failed - no results generated" in result.output


# --------------------------------------------------------------------------- #
# integrate — read-error, transform-failure fallback, integration failure
# --------------------------------------------------------------------------- #


def test_integrate_reports_read_error(runner, tmp_path):
    # A directory passes click's exists=True but open() raises IsADirectoryError,
    # exercising the generic read-error branch.
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    a_dir = tmp_path / "analysis_dir"
    a_dir.mkdir()
    result = runner.invoke(project, ["integrate", "--analysis", str(a_dir), "--project", str(proj)])
    _no_crash(result)
    assert "Failed to read analysis file" in result.output


def test_integrate_falls_back_to_raw_on_transform_error(runner, tmp_path):
    # A top-level YAML list makes transform_analysis_to_integration_format raise
    # (list has no .get); the command warns and continues with the raw data.
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    analysis = tmp_path / "an.yaml"
    analysis.write_text(yaml.dump(["not", "a", "dict"]), encoding="utf-8")
    result = runner.invoke(project, ["integrate", "--analysis", str(analysis), "--project", str(proj)])
    _no_crash(result)
    assert "Could not transform analysis data" in result.output


def test_integrate_reports_integration_failure(runner, tmp_path):
    # A valid analysis but a *file* as the project makes ProjectIntegrator fail
    # (cannot create config/ under a file), hitting the integration-error branch.
    proj_file = tmp_path / "proj_file"
    proj_file.write_text("x", encoding="utf-8")
    analysis = tmp_path / "an.yaml"
    analysis.write_text(yaml.dump({"user_flows": [], "api_contracts": []}), encoding="utf-8")
    result = runner.invoke(project, ["integrate", "--analysis", str(analysis), "--project", str(proj_file)])
    _no_crash(result)
    assert "Integration failed" in result.output


# --------------------------------------------------------------------------- #
# generate — full artifact set, and the nothing-generated case
# --------------------------------------------------------------------------- #


def _project_with_full_model(tmp_path: Path) -> Path:
    """A model whose screens, api_calls and flows all yield generated artifacts."""
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    model = {
        "meta": {
            "schema_version": "1.0.0",
            "app_version": "1.0.0",
            "platform": "android",
            "recorded_at": "2025-01-01T00:00:00Z",
        },
        "screens": {
            "LoginScreen": {
                "name": "LoginScreen",
                "elements": [
                    {
                        "id": "login_btn",
                        "type": "button",
                        "selector": {"android": "id:login"},
                        "capabilities": ["tappable"],
                    }
                ],
                "actions": [
                    {"name": "do_login", "ui_action": "tap", "element_id": "login_btn"},
                ],
            }
        },
        "api_calls": {"auth_login": {"name": "auth_login", "endpoint": "/login", "method": "POST"}},
        "flows": [{"name": "LoginFlow", "steps": [{"screen": "LoginScreen", "action": "tap"}]}],
    }
    (proj / "config" / "app_model.yaml").write_text(yaml.dump(model), encoding="utf-8")
    return proj


def test_generate_emits_all_artifact_kinds(runner, tmp_path):
    proj = _project_with_full_model(tmp_path)
    result = runner.invoke(project, ["generate", "--project", str(proj)])
    _no_crash(result)
    assert result.exit_code == 0
    out = result.output
    # Each stats>0 summary line and the BDD "pytest --bdd" next-step must appear.
    assert "Page Objects" in out
    assert "Integration Tests" in out
    assert "API Endpoints" in out
    assert "BDD Features" in out
    assert "pytest --bdd" in out
    # Artifacts really landed on disk.
    assert (proj / "page_objects").exists()
    assert (proj / "features").exists()


def test_generate_reports_nothing_generated(runner, tmp_path):
    # A model with only a meta block (no screens/api/flows) produces no artifacts.
    proj = tmp_path / "proj"
    (proj / "config").mkdir(parents=True)
    model = {
        "meta": {
            "schema_version": "1.0.0",
            "app_version": "1.0.0",
            "platform": "android",
            "recorded_at": "2025-01-01T00:00:00Z",
        }
    }
    (proj / "config" / "app_model.yaml").write_text(yaml.dump(model), encoding="utf-8")
    result = runner.invoke(project, ["generate", "--project", str(proj)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No code was generated" in result.output


# --------------------------------------------------------------------------- #
# fullcycle — iOS phase, and the all-analyses-failed short-circuit
# --------------------------------------------------------------------------- #


def test_fullcycle_ios_source(runner, tmp_path):
    proj = tmp_path / "auto"
    result = runner.invoke(project, ["fullcycle", "--ios-path", str(_swift_source(tmp_path)), "--project", str(proj)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Phase 1b: Analyzing iOS Source" in result.output
    assert (proj / "analysis" / "ios_analysis.yaml").exists()


def test_fullcycle_all_analyses_fail(runner, tmp_path):
    # Pre-create the android output name as a *directory* so the phase-1 write
    # raises; with no other source, fullcycle short-circuits before integration.
    proj = tmp_path / "auto"
    (proj / "analysis").mkdir(parents=True)
    (proj / "analysis" / "android_analysis.yaml").mkdir()
    result = runner.invoke(
        project, ["fullcycle", "--android-path", str(_source_tree(tmp_path)), "--project", str(proj)]
    )
    _no_crash(result)
    assert "Android analysis failed" in result.output
    assert "All analyses failed" in result.output


def test_fullcycle_ios_analysis_fails(runner, tmp_path):
    # Same failure injection for the iOS phase: its output name is a directory.
    proj = tmp_path / "auto"
    (proj / "analysis").mkdir(parents=True)
    (proj / "analysis" / "ios_analysis.yaml").mkdir()
    result = runner.invoke(project, ["fullcycle", "--ios-path", str(_swift_source(tmp_path)), "--project", str(proj)])
    _no_crash(result)
    assert "iOS analysis failed" in result.output
    assert "All analyses failed" in result.output
