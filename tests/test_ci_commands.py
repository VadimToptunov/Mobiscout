"""Behavior tests for the `ci` CLI group (CI/CD config scaffolding).

Uses the real template registry: `init` writes an actual config file (and honours
the overwrite prompt), `show`/`list-templates`/`quickstart` render templates, and
`validate` runs the per-system checks against good, empty, and unknown configs.
"""

import pytest
from click.testing import CliRunner

from framework.cli.ci_commands import ci


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def test_list_templates(runner):
    result = runner.invoke(ci, ["list-templates"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "GitHub Actions" in result.output


@pytest.mark.parametrize("system", ["github", "gitlab", "jenkins", "circleci"])
def test_show_renders_template(runner, system):
    result = runner.invoke(ci, ["show", system, "-t", "basic"])
    _no_crash(result)
    assert result.exit_code == 0
    assert system.upper() in result.output


def test_init_writes_file(runner, tmp_path):
    out = tmp_path / "workflow.yml"
    # Answer "n" to the "show file contents?" prompt so no pager interaction.
    result = runner.invoke(ci, ["init", "github", "-o", str(out)], input="n\n")
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()
    assert out.read_text(encoding="utf-8").strip()


def test_init_overwrite_declined_keeps_file(runner, tmp_path):
    out = tmp_path / "workflow.yml"
    out.write_text("original: content\n", encoding="utf-8")
    # Decline the overwrite prompt -> file left untouched, command cancels.
    result = runner.invoke(ci, ["init", "github", "-o", str(out)], input="n\n")
    _no_crash(result)
    assert "Cancelled" in result.output
    assert out.read_text(encoding="utf-8") == "original: content\n"


def test_validate_good_github_config(runner, tmp_path):
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    config = workflow / "tests.yml"
    config.write_text(
        "name: Tests\non:\n  push:\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    result = runner.invoke(ci, ["validate", str(config)])
    _no_crash(result)
    assert "looks good" in result.output


def test_validate_reports_missing_fields(runner, tmp_path):
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    config = workflow / "tests.yml"
    # Valid YAML but missing required GitHub Actions keys.
    config.write_text("foo: bar\n", encoding="utf-8")
    result = runner.invoke(ci, ["validate", str(config)])
    _no_crash(result)
    assert "Validation failed" in result.output
    assert "jobs" in result.output


def test_validate_empty_github_yaml_exits_one(runner, tmp_path):
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    config = workflow / "tests.yml"
    config.write_text("", encoding="utf-8")
    result = runner.invoke(ci, ["validate", str(config)])
    _no_crash(result)
    assert result.exit_code == 1
    assert "empty or invalid" in result.output


def test_validate_missing_file(runner, tmp_path):
    result = runner.invoke(ci, ["validate", str(tmp_path / "nope.yml")])
    _no_crash(result)
    assert "File not found" in result.output


def test_validate_unknown_system(runner, tmp_path):
    config = tmp_path / "random.txt"
    config.write_text("hello: world\n", encoding="utf-8")
    result = runner.invoke(ci, ["validate", str(config)])
    _no_crash(result)
    assert "Unknown CI system" in result.output


def test_quickstart(runner):
    result = runner.invoke(ci, ["quickstart"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Quick Start" in result.output
