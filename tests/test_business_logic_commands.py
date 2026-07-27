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


# --------------------------------------------------------------------------- #
# `business analyze` — the summary/display block over a real Android tree
# --------------------------------------------------------------------------- #


def _rich_android_project(tmp_path: Path) -> Path:
    """A Kotlin source tree deliberately rich enough to exercise every summary
    section of `business analyze`, including the "... and N more" overflow lines
    (needs >5 flows, >3 state machines, >5 data models)."""
    root = tmp_path / "android"
    root.mkdir()

    # 6 ViewModels -> 6 user flows (>5 triggers the overflow line).
    for i in range(6):
        (root / f"Feature{i}ViewModel.kt").write_text(
            f"class Feature{i}ViewModel {{\n    fun load{i}() {{ }}\n    fun submit{i}() {{ }}\n}}\n",
            encoding="utf-8",
        )

    # 4 sealed *State classes -> 4 state machines (>3 triggers the overflow line).
    for i in range(4):
        (root / f"State{i}.kt").write_text(
            f"sealed class Screen{i}State {{\n"
            f"    data class Loading{i}(val x: Int)\n"
            f"    data class Loaded{i}(val y: Int)\n"
            f"    data class Error{i}(val z: Int)\n"
            "}\n",
            encoding="utf-8",
        )

    # 6 data models (>5 triggers the overflow line).
    models = root / "models"
    models.mkdir()
    for i in range(6):
        (models / f"Model{i}.kt").write_text(
            f"data class Model{i}(val id: Int, val name: String)\n",
            encoding="utf-8",
        )

    # Mock data with an ID range -> Android-style mock entity.
    mock = root / "mock"
    mock.mkdir()
    (mock / "MockUsers.kt").write_text(
        "val MockData.Users get() = users\nval users by lazy { (1L..10L).map { it } }\n",
        encoding="utf-8",
    )

    # Retrofit interface -> one API contract.
    (root / "ApiService.kt").write_text(
        "interface ApiService {\n"
        '    @Headers("Authorization: Bearer")\n'
        '    @POST("/login") suspend fun login(@Body req: LoginRequest): LoginResponse\n'
        "}\n",
        encoding="utf-8",
    )

    # Validator -> boundary + null + empty edge cases.
    (root / "Validator.kt").write_text(
        "fun validate(user: String?, items: List) {\n"
        "    if (age > 18) { }\n"
        "    if (user != null) { }\n"
        "    if (items.isEmpty()) { }\n"
        "}\n",
        encoding="utf-8",
    )
    return root


def test_analyze_displays_every_summary_section(runner, tmp_path):
    out = tmp_path / "bl.yaml"
    result = runner.invoke(
        business,
        ["analyze", "--source", str(_rich_android_project(tmp_path)), "--output", str(out)],
    )
    _no_crash(result)
    assert result.exit_code == 0

    # Each optional section header is rendered because the tree produced data.
    for header in [
        "User Flows:",
        "State Machines:",
        "Edge Cases:",
        "Data Models:",
        "Mock Test Data:",
        "API Contracts:",
    ]:
        assert header in result.output, f"missing section: {header}"

    # Overflow lines fire for the sections that exceed their display cap.
    assert "and 1 more" in result.output  # 6 flows shown 5 -> 1 more; 4 SMs shown 3 -> 1 more; 6 models shown 5 -> 1
    # Android-style mock data reports its ID range.
    assert "IDs 1-10" in result.output
    assert out.exists()


# --------------------------------------------------------------------------- #
# JSON input branch for every display/generation subcommand
# --------------------------------------------------------------------------- #


def _analysis_json(tmp_path: Path) -> Path:
    """Same payload as `_analysis_file` but as .json, to drive the
    `input_file.endswith('.json')` json.load branch in each subcommand."""
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
        "mock_data": {"User": {"count": 5, "start_id": 1, "end_id": 5, "source": "db.json"}},
        "edge_cases": [{"type": "boundary", "description": "empty", "severity": "high", "test_data": [""]}],
        "state_machines": [
            {"name": "Auth", "states": ["idle", "done"], "initial_state": "idle", "transitions": {"idle": ["done"]}}
        ],
        "negative_test_cases": [{"name": "wrong password", "expected_outcome": "reject", "priority": "high"}],
        "api_contracts": [{"method": "POST", "endpoint": "/login", "description": "auth", "source_file": "api.kt"}],
    }
    path = tmp_path / "bl.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("cmd", ["scenarios", "features", "testdata", "edgecases", "statemachines", "contracts"])
def test_subcommands_accept_json_input(runner, tmp_path, cmd):
    # The .json suffix must route through json.load rather than yaml.safe_load.
    result = runner.invoke(business, [cmd, "--input", str(_analysis_json(tmp_path))])
    _no_crash(result)
    assert result.exit_code == 0


def test_negative_accepts_json_input(runner, tmp_path):
    out = tmp_path / "neg.yaml"
    result = runner.invoke(business, ["negative", "--input", str(_analysis_json(tmp_path)), "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "HIGH Priority" in result.output


# --------------------------------------------------------------------------- #
# Empty / overflow / optional-field branches
# --------------------------------------------------------------------------- #


def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def test_features_preview_truncates_long_output(runner, tmp_path):
    # Two flows push the generated gherkin past the 15-line preview cap.
    data = {
        "user_flows": [
            {
                "name": f"Flow{i}",
                "description": f"desc {i}",
                "steps": ["a", "b", "c"],
                "entry_point": f"Screen{i}",
                "success_outcome": "ok",
            }
            for i in range(2)
        ]
    }
    out = tmp_path / "features" / "bl.feature"
    result = runner.invoke(
        business, ["features", "--input", str(_write_yaml(tmp_path, "bl.yaml", data)), "--output", str(out)]
    )
    _no_crash(result)
    assert result.exit_code == 0
    assert "..." in result.output


def test_testdata_renders_generic_mock_entity(runner, tmp_path):
    # A mock entity without ID range and without a 'type' hits the generic branch.
    path = _write_yaml(tmp_path, "bl.yaml", {"mock_data": {"Config": {"count": 2, "source": "seed.json"}}})
    result = runner.invoke(business, ["testdata", "--input", str(path)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Config" in result.output
    assert "Records: 2" in result.output


def test_edgecases_empty_message(runner, tmp_path):
    path = _write_yaml(tmp_path, "bl.yaml", {"edge_cases": []})
    result = runner.invoke(business, ["edgecases", "--input", str(path)])
    _no_crash(result)
    assert "No edge cases detected" in result.output


def test_edgecases_truncates_per_type(runner, tmp_path):
    # >5 cases of one type triggers the "... and N more" line.
    cases = [{"type": "boundary", "description": f"case {i}", "severity": "high", "test_data": [i]} for i in range(7)]
    path = _write_yaml(tmp_path, "bl.yaml", {"edge_cases": cases})
    result = runner.invoke(business, ["edgecases", "--input", str(path)])
    _no_crash(result)
    assert "and 2 more" in result.output


def test_statemachines_empty_message(runner, tmp_path):
    path = _write_yaml(tmp_path, "bl.yaml", {"state_machines": []})
    result = runner.invoke(business, ["statemachines", "--input", str(path)])
    _no_crash(result)
    assert "No state machines detected" in result.output


def test_negative_empty_message(runner, tmp_path):
    out = tmp_path / "neg.yaml"
    path = _write_yaml(tmp_path, "bl.yaml", {"negative_test_cases": []})
    result = runner.invoke(business, ["negative", "--input", str(path), "--output", str(out)])
    _no_crash(result)
    assert "No negative test cases generated" in result.output


def test_negative_truncates_per_priority(runner, tmp_path):
    out = tmp_path / "neg.yaml"
    tests = [{"name": f"t{i}", "expected_outcome": "reject", "priority": "high"} for i in range(7)]
    path = _write_yaml(tmp_path, "bl.yaml", {"negative_test_cases": tests})
    result = runner.invoke(business, ["negative", "--input", str(path), "--output", str(out)])
    _no_crash(result)
    assert "and 2 more" in result.output


def test_contracts_empty_message(runner, tmp_path):
    path = _write_yaml(tmp_path, "bl.yaml", {"api_contracts": []})
    result = runner.invoke(business, ["contracts", "--input", str(path)])
    _no_crash(result)
    assert "No API contracts found" in result.output


def test_contracts_renders_all_optional_fields(runner, tmp_path):
    contract = {
        "method": "POST",
        "endpoint": "/login",
        "description": "Authenticate user",
        "authentication": "Bearer Token",
        "request_schema": {
            "body": {"username": "String"},
            "query": {"lang": "String"},
            "path": {"id": "Int"},
        },
        "response_schema": {"type": "LoginResponse"},
        "error_responses": [{"code": "401"}, {"code": "500"}],
        "source_file": "api.kt",
    }
    path = _write_yaml(tmp_path, "bl.yaml", {"api_contracts": [contract]})
    result = runner.invoke(business, ["contracts", "--input", str(path)])
    _no_crash(result)
    assert result.exit_code == 0
    out = result.output
    assert "Description: Authenticate user" in out
    assert "Auth: Bearer Token" in out
    assert "Body:" in out and "Query params:" in out and "Path params:" in out
    assert "Response: LoginResponse" in out
    assert "Errors: 2 defined" in out
    assert "Source: api.kt" in out


def test_complexity_json_format_and_recommendations(runner, tmp_path):
    # A high-complexity function drives the recommendation branch; JSON exercises
    # the json.dump output path and the "Most Complex Functions" listing.
    #
    # ASTAnalyzer.analyze_python skips any path containing the substring "test"
    # (ast_analyzer.py:93) — and every pytest tmp path contains "pytest" — so the
    # source tree must live outside the pytest tmp dir to actually be analyzed.
    import shutil
    import tempfile

    src = Path(tempfile.mkdtemp(prefix="mobiscout_cc_"))
    try:
        body = (
            "def big(x):\n    t = 0\n"
            + "".join(f"    if x == {i}:\n        t += {i}\n" for i in range(14))
            + "    return t\n"
        )
        (src / "big.py").write_text(body, encoding="utf-8")
        out = tmp_path / "cc.json"
        result = runner.invoke(business, ["complexity", "--source", str(src), "--output", str(out), "--format", "json"])
        _no_crash(result)
        assert result.exit_code == 0
        assert "Most Complex Functions" in result.output
        assert "big:" in result.output
        assert "high complexity" in result.output.lower()
        # File is real JSON.
        assert isinstance(json.loads(out.read_text(encoding="utf-8")), dict)
    finally:
        shutil.rmtree(src, ignore_errors=True)
