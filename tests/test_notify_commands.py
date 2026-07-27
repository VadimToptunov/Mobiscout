"""Behaviour tests for the `mobiscout notify` CLI group (framework/cli/notify_commands.py).

The config file is redirected into tmp_path (the real command writes to
~/.mobiscout/config.json), so configure/list round-trip on a real JSON file.
The webhook HTTP POST is the only external I/O and is faked; the JUnit parsing,
summary calculation, channel wiring and result formatting all run for real.
"""

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from framework.cli import notify_commands as nc
from framework.notifications import notifiers as notifiers_mod
from framework.cli.notify_commands import notify


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


@pytest.fixture()
def config_file(tmp_path, monkeypatch):
    """Redirect the module-level CONFIG_FILE at a tmp path (never touch $HOME)."""
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(nc, "CONFIG_FILE", cfg)
    return cfg


@pytest.fixture()
def slack_configured(config_file):
    config_file.write_text(json.dumps({"notification_slack_webhook": "https://hooks.slack.test/abc"}))
    return config_file


@pytest.fixture()
def webhook_ok(monkeypatch):
    """Make every webhook POST succeed without hitting the network."""
    monkeypatch.setattr(notifiers_mod.requests, "post", lambda *a, **k: SimpleNamespace(raise_for_status=lambda: None))


# --- configure ---------------------------------------------------------------


def test_configure_slack_persists(runner, config_file):
    result = runner.invoke(notify, ["configure", "--slack-webhook", "https://hooks.slack.test/xyz"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Slack webhook configured" in result.output
    saved = json.loads(config_file.read_text())
    assert saved["notification_slack_webhook"] == "https://hooks.slack.test/xyz"


def test_configure_no_args_aborts(runner, config_file):
    result = runner.invoke(notify, ["configure"])
    _no_crash(result)
    assert result.exit_code != 0
    assert "No configuration provided" in result.output
    assert not config_file.exists()  # nothing written


def test_configure_partial_email_aborts(runner, config_file):
    result = runner.invoke(notify, ["configure", "--email-smtp", "smtp.test:587"])
    _no_crash(result)
    assert result.exit_code != 0
    assert "requires all three options" in result.output


# --- list --------------------------------------------------------------------


def test_list_channels_empty(runner, config_file):
    result = runner.invoke(notify, ["list"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No notification channels configured" in result.output


def test_list_channels_shows_slack(runner, slack_configured):
    result = runner.invoke(notify, ["list"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Slack" in result.output


# --- test --------------------------------------------------------------------


def test_test_without_config_aborts(runner, config_file):
    result = runner.invoke(notify, ["test"])
    _no_crash(result)
    assert result.exit_code != 0
    assert "No all notification configured" in result.output


def test_test_sends_via_slack(runner, slack_configured, webhook_ok):
    result = runner.invoke(notify, ["test", "--channel", "slack"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "SlackNotifier" in result.output
    assert "Sent successfully" in result.output


# --- send --------------------------------------------------------------------


_JUNIT_XML = """<?xml version="1.0"?>
<testsuite name="suite" tests="2" failures="1" time="1.5">
  <testcase name="test_pass" classname="mod" time="0.5"/>
  <testcase name="test_fail" classname="mod" time="1.0">
    <failure message="boom">trace</failure>
  </testcase>
</testsuite>
"""

_EMPTY_JUNIT_XML = """<?xml version="1.0"?>
<testsuite name="suite" tests="0"></testsuite>
"""


def test_send_notifies_from_junit(runner, tmp_path, slack_configured, webhook_ok):
    xml = tmp_path / "results.xml"
    xml.write_text(_JUNIT_XML)
    result = runner.invoke(notify, ["send", "-j", str(xml), "--channel", "slack", "--platform", "Android"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Total: 2" in result.output
    assert "Passed: 1" in result.output
    assert "SlackNotifier" in result.output


def test_send_empty_results_aborts(runner, tmp_path, slack_configured):
    xml = tmp_path / "empty.xml"
    xml.write_text(_EMPTY_JUNIT_XML)
    result = runner.invoke(notify, ["send", "-j", str(xml)])
    _no_crash(result)
    assert result.exit_code != 0
    assert "No test results found" in result.output


def test_send_no_channel_configured_aborts(runner, tmp_path, config_file):
    xml = tmp_path / "results.xml"
    xml.write_text(_JUNIT_XML)
    result = runner.invoke(notify, ["send", "-j", str(xml)])
    _no_crash(result)
    assert result.exit_code != 0
    assert "No all notification configured" in result.output


# --- on-healing --------------------------------------------------------------


def test_on_healing_sends(runner, tmp_path, slack_configured, webhook_ok):
    healing = tmp_path / "healing.json"
    healing.write_text(json.dumps({"healed_count": 3, "failed_count": 1}))
    result = runner.invoke(notify, ["on-healing", "-h", str(healing), "--channel", "slack"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "SlackNotifier" in result.output
    assert "Sent" in result.output
