"""Behaviour tests for `mobiscout selector` (parse/examples/operators/relationships/benchmark).

Runs the real selector engine and Appium conversion — the `parse` command builds
a real ``AdvancedSelector`` and emits its Appium locator, and `benchmark` actually
exercises the engine over a 1000-element hierarchy. Nothing is mocked; these are
pure in-process CPU/logic paths.
"""

import pytest
from click.testing import CliRunner

from framework.cli.selector_commands import selector


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def test_parse_id_selector(runner):
    result = runner.invoke(selector, ["parse", "#login_button"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Type: ID" in result.output
    assert "login_button" in result.output
    # ID selectors convert to an Appium accessibility/id locator.
    assert "'id': 'login_button'" in result.output


def test_parse_class_selector(runner):
    result = runner.invoke(selector, ["parse", ".Button"])
    _no_crash(result)
    assert "Type: Class" in result.output


def test_parse_text_selector_ios(runner):
    result = runner.invoke(selector, ["parse", "Login", "--platform", "ios"])
    _no_crash(result)
    assert "Type: Text" in result.output
    # Text selector renders an xpath locator carrying the text value.
    assert "Login" in result.output


def test_examples_renders(runner):
    result = runner.invoke(selector, ["examples"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Selector Examples" in result.output


def test_operators_lists_all(runner):
    result = runner.invoke(selector, ["operators"])
    _no_crash(result)
    assert "EQUALS" in result.output and "HAS_ATTRIBUTE" in result.output


def test_relationships_lists_all(runner):
    result = runner.invoke(selector, ["relationships"])
    _no_crash(result)
    assert "PARENT" in result.output and "DESCENDANT" in result.output


def test_benchmark_runs_over_real_engine(runner):
    result = runner.invoke(selector, ["benchmark"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Benchmark Results" in result.output
    assert "ID lookup" in result.output
    assert "completed successfully" in result.output
