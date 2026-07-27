"""Behaviour tests for the `mobiscout heal` CLI group (framework/cli/healing_commands.py).

These drive the self-healing commands over real JUnit XML fixtures and a real
SQLite dashboard DB (built in tmp_path) so the tests exercise the genuine
FailureAnalyzer / HealingOrchestrator / DashboardDB code paths — no mocking of
the logic under test. Only `heal revert` shells out to git, and is exercised via
its deterministic failure path (a bad hash in a non-repo).
"""

from datetime import datetime

import pytest
from click.testing import CliRunner

from pathlib import Path

from framework.cli import healing_commands as hc
from framework.cli.healing_commands import heal
from framework.dashboard.database import DashboardDB
from framework.dashboard.models import HealedSelector, HealingStatus
from framework.healing.failure_analyzer import FailureType, SelectorFailure


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


# A JUnit failure whose message matches both a selector-failure pattern and the
# Appium Using='...'/value='...' selector-extraction regex.
_SELECTOR_FAIL_XML = """<?xml version="1.0"?>
<testsuite name="ui" tests="1" failures="1">
  <testcase name="test_login" classname="tests.login">
    <failure message="Unable to find element Using='id', value='login_btn'">stacktrace</failure>
  </testcase>
</testsuite>
"""

_PASSING_XML = """<?xml version="1.0"?>
<testsuite name="ui" tests="1" failures="0">
  <testcase name="test_ok" classname="tests.ok" time="0.1"/>
</testsuite>
"""


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_analyze_finds_failure_but_no_candidates_without_page_source(runner, tmp_path):
    xml = _write(tmp_path, "results.xml", _SELECTOR_FAIL_XML)
    result = runner.invoke(heal, ["analyze", "-t", str(xml), "--repo", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Found 1 test failures" in result.output
    # No captured page source => nothing to discover alternatives from.
    assert "No healing candidates found" in result.output


def test_analyze_reports_no_failures(runner, tmp_path):
    xml = _write(tmp_path, "results.xml", _PASSING_XML)
    result = runner.invoke(heal, ["analyze", "-t", str(xml), "--repo", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No test failures found" in result.output


def test_analyze_missing_results_errors(runner, tmp_path):
    result = runner.invoke(heal, ["analyze", "-t", str(tmp_path / "missing.xml")])
    _no_crash(result)
    assert result.exit_code != 0  # click.Path(exists=True) rejects it


def test_auto_dry_run(runner, tmp_path):
    xml = _write(tmp_path, "results.xml", _SELECTOR_FAIL_XML)
    result = runner.invoke(heal, ["auto", "-t", str(xml), "--repo", str(tmp_path), "--dry-run"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    assert "Found 1 test failures" in result.output


def test_auto_real_reports_failure_without_page_source(runner, tmp_path):
    # Non-dry-run drives the orchestrator; with no page source it cannot heal and
    # must report the failure honestly rather than claiming success.
    xml = _write(tmp_path, "results.xml", _SELECTOR_FAIL_XML)
    result = runner.invoke(heal, ["auto", "-t", str(xml), "--repo", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Failed to heal: 1/1" in result.output


def _make_db_with_history(repo_path):
    db = DashboardDB(repo_path / ".dashboard.db")
    db.add_healed_selector(
        HealedSelector(
            id="h1",
            test_name="test_login",
            element_name="login_button",
            file_path="pages/login.py",
            old_selector_type="id",
            old_selector_value="login_btn",
            new_selector_type="accessibility_id",
            new_selector_value="Login",
            confidence=0.92,
            strategy="accessibility_id",
            status=HealingStatus.APPROVED,
            timestamp=datetime.now(),
        )
    )
    db.close()


def test_history_without_db_aborts(runner, tmp_path):
    result = runner.invoke(heal, ["history", "--repo", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code != 0
    assert "No healing history found" in result.output


def test_history_shows_recorded_actions(runner, tmp_path):
    _make_db_with_history(tmp_path)
    result = runner.invoke(heal, ["history", "--repo", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "test_login" in result.output
    assert "Total healing actions: 1" in result.output


def test_stats_without_db_aborts(runner, tmp_path):
    result = runner.invoke(heal, ["stats", "--repo", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code != 0
    assert "No healing statistics found" in result.output


def test_stats_computes_success_rate(runner, tmp_path):
    _make_db_with_history(tmp_path)
    result = runner.invoke(heal, ["stats", "--repo", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Total healing actions: 1" in result.output
    # One approved, zero rejected => 100% success rate.
    assert "100.0%" in result.output


# An Appium/Android page-source dump with discoverable interactive elements.
_PAGE_SOURCE_XML = """<?xml version="1.0"?>
<hierarchy>
  <android.widget.Button resource-id="com.app:id/login" text="Login" clickable="true"/>
  <android.widget.EditText resource-id="com.app:id/user" text="Username"/>
</hierarchy>
"""


def _failure_with_page_source(tmp_path):
    ps = _write(tmp_path, "page_source.xml", _PAGE_SOURCE_XML)
    return SelectorFailure(
        test_name="test_login",
        test_file=Path("tests/test_login.py"),
        selector_type="id",
        selector_value="old_login_id",
        failure_type=FailureType.SELECTOR_NOT_FOUND,
        error_message="Unable to find element",
        page_source_path=ps,
    )


def test_analyze_finds_candidates_with_page_source(runner, tmp_path, monkeypatch):
    # Inject a failure that carries a captured page source; real SelectorDiscovery
    # then finds alternative selectors from it.
    failure = _failure_with_page_source(tmp_path)
    monkeypatch.setattr(hc.FailureAnalyzer, "analyze_test_results", lambda self, *a, **k: [failure])

    xml = _write(tmp_path, "results.xml", _SELECTOR_FAIL_XML)
    result = runner.invoke(heal, ["analyze", "-t", str(xml), "--repo", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Found 1 healing candidates" in result.output
    assert "test_login" in result.output


def test_auto_dry_run_heals_candidate_with_page_source(runner, tmp_path, monkeypatch):
    failure = _failure_with_page_source(tmp_path)
    monkeypatch.setattr(hc.FailureAnalyzer, "analyze_test_results", lambda self, *a, **k: [failure])

    xml = _write(tmp_path, "results.xml", _SELECTOR_FAIL_XML)
    result = runner.invoke(heal, ["auto", "-t", str(xml), "--repo", str(tmp_path), "--dry-run"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Successfully healed: 1/1" in result.output


def test_revert_bad_commit_aborts(runner, tmp_path):
    # tmp_path is not a git repo, so `git revert deadbeef` fails cleanly.
    result = runner.invoke(heal, ["revert", "deadbeef", "--repo", str(tmp_path)])
    _no_crash(result)
    assert result.exit_code != 0
