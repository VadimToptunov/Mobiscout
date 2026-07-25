"""`mobiscout source analyze` wires the previously-unreachable Android source
analyzer (framework/analyzers) to the CLI: statically map a Kotlin/Compose project
into screens / elements / routes / API endpoints. Drives it over a tiny fixture.
"""

import json
import textwrap

import pytest
from click.testing import CliRunner

from framework.cli.source_commands import source

_KOTLIN = textwrap.dedent("""
    @Composable
    fun LoginScreen() {
        Button(modifier = Modifier.testTag("login_button")) { Text("Login") }
    }

    interface AuthApi {
        @POST("auth/login")
        suspend fun login(): Token
    }
    """)


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "LoginScreen.kt").write_text(_KOTLIN, encoding="utf-8")
    return tmp_path


def test_source_analyze_runs(runner, project):
    result = runner.invoke(source, ["analyze", str(project)])
    assert result.exit_code == 0, result.output
    assert "Kotlin file" in result.output


def test_source_analyze_finds_composable_and_endpoint(runner, project, tmp_path):
    out = tmp_path / "analysis.json"
    result = runner.invoke(source, ["analyze", str(project), "--output", str(out)])
    assert result.exit_code == 0, result.output

    data = json.loads(out.read_text())
    assert data["files_analyzed"] == 1
    composables = {s.get("composable_name") for s in data["screens"]}
    assert "LoginScreen" in composables
    endpoints = {(e["method"], e["path"]) for e in data["api_endpoints"]}
    assert ("POST", "auth/login") in endpoints
