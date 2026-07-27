"""Behaviour tests for the notification providers (framework/notifications/notifiers.py).

The webhook HTTP POST (Slack/Teams) and the SMTP send (email) are the only
external I/O and are stubbed; everything else runs for real. The stubs *capture*
the payload the notifier built so we can assert its structure — colour by pass
rate, the fields/facts, platform insertion, report/build links, and the manager
fan-out.

Regression note: SlackNotifier / TeamsNotifier previously called
``requests.post(url, headers=...)`` and never passed the ``message`` body, so the
carefully built payload was silently dropped. These tests assert the JSON body is
actually sent, and would fail against that bug.
"""

import smtplib
from email.message import Message

import pytest
import requests

from framework.notifications import notifiers as notifiers_mod
from framework.notifications.notifiers import (
    EmailNotifier,
    NotificationManager,
    Notifier,
    SlackNotifier,
    TeamsNotifier,
    TestSummary,
)


class _CapturingPost:
    """Fake requests.post that records the last call and succeeds."""

    def __init__(self, raise_exc=None):
        self.calls = []
        self._raise_exc = raise_exc

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self._raise_exc:
            raise self._raise_exc

        class _Resp:
            def raise_for_status(_self):
                return None

        return _Resp()

    @property
    def last(self):
        return self.calls[-1]


def _summary(pass_rate=100.0, **kw):
    defaults = dict(total=10, passed=10, failed=0, skipped=0, duration=12.3, pass_rate=pass_rate)
    defaults.update(kw)
    return TestSummary(**defaults)


# --- SlackNotifier -----------------------------------------------------------


def test_slack_sends_built_payload(monkeypatch):
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)

    ok = SlackNotifier("https://hooks.slack.test/x").send(_summary(passed=8, failed=2, pass_rate=80.0), title="Nightly")
    assert ok is True

    call = post.last
    assert call["url"] == "https://hooks.slack.test/x"
    body = call["json"]  # payload must actually be sent (regression guard)
    assert body["text"] == "*Nightly*"
    attachment = body["attachments"][0]
    assert attachment["color"] == "#ff9900"  # 80% -> orange
    field_titles = {f["title"] for f in attachment["fields"]}
    assert {"Total Tests", "Pass Rate", "Passed", "Failed", "Skipped", "Duration"} <= field_titles


def test_slack_color_green_for_high_pass_rate(monkeypatch):
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    SlackNotifier("u").send(_summary(pass_rate=99.0))
    assert post.last["json"]["attachments"][0]["color"] == "#36a64f"


def test_slack_color_red_for_low_pass_rate(monkeypatch):
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    SlackNotifier("u").send(_summary(passed=1, failed=9, pass_rate=10.0))
    assert post.last["json"]["attachments"][0]["color"] == "#d00000"


def test_slack_adds_platform_and_report_link(monkeypatch):
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    SlackNotifier("u").send(_summary(platform="Android", report_url="https://report.test/1"))
    attachment = post.last["json"]["attachments"][0]
    assert attachment["fields"][0] == {"title": "Platform", "value": "Android", "short": True}
    assert attachment["actions"][0]["url"] == "https://report.test/1"


def test_slack_returns_false_on_http_error(monkeypatch):
    post = _CapturingPost(raise_exc=requests.RequestException("boom"))
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    assert SlackNotifier("u").send(_summary()) is False


def test_slack_green_color_is_six_hex_digits(monkeypatch):
    # Bug 4: the green color was "#36a64" (5 hex digits, invalid CSS/Slack color).
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    SlackNotifier("u").send(_summary(pass_rate=99.0))
    color = post.last["json"]["attachments"][0]["color"]
    assert color == "#36a64f"
    assert len(color) == 7 and color.startswith("#")
    int(color[1:], 16)  # parses as a valid 6-digit hex color


def test_slack_passes_timeout(monkeypatch):
    # Bug 3: requests.post had no timeout -> a hung webhook blocks forever.
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    SlackNotifier("u").send(_summary())
    assert post.last["timeout"] == (5, 10)


def test_slack_returns_false_on_timeout(monkeypatch):
    # Bug 3: a timeout must be caught and reported as failure, not propagate.
    post = _CapturingPost(raise_exc=requests.Timeout("slow"))
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    assert SlackNotifier("u").send(_summary()) is False


# --- TeamsNotifier -----------------------------------------------------------


def test_teams_sends_message_card(monkeypatch):
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    ok = TeamsNotifier("https://teams.test/x").send(
        _summary(passed=8, failed=2, pass_rate=80.0, platform="iOS"), title="CI"
    )
    assert ok is True
    body = post.last["json"]
    assert body["@type"] == "MessageCard"
    assert body["themeColor"] == "ffc107"  # 80% -> yellow
    facts = body["sections"][0]["facts"]
    assert facts[0] == {"name": "Platform", "value": "iOS"}
    fact_names = {f["name"] for f in facts}
    assert {"Total Tests", "Passed", "Failed", "Pass Rate", "Duration"} <= fact_names


def test_teams_adds_report_and_build_actions(monkeypatch):
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    TeamsNotifier("u").send(_summary(report_url="https://r.test", build_url="https://b.test"))
    actions = post.last["json"]["potentialAction"]
    uris = {a["targets"][0]["uri"] for a in actions}
    assert uris == {"https://r.test", "https://b.test"}


def test_teams_returns_false_on_http_error(monkeypatch):
    post = _CapturingPost(raise_exc=requests.RequestException("down"))
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    assert TeamsNotifier("u").send(_summary()) is False


def test_teams_passes_timeout(monkeypatch):
    # Bug 3: requests.post had no timeout.
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    TeamsNotifier("u").send(_summary())
    assert post.last["timeout"] == (5, 10)


def test_teams_returns_false_on_timeout(monkeypatch):
    post = _CapturingPost(raise_exc=requests.Timeout("slow"))
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    assert TeamsNotifier("u").send(_summary()) is False


# --- EmailNotifier -----------------------------------------------------------


class _FakeSMTP:
    """Context-manager stand-in for smtplib.SMTP that records sent messages."""

    sent = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.tls = False
        self.logged_in = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, pwd):
        self.logged_in = (user, pwd)

    def send_message(self, msg):
        type(self).sent.append(msg)


def test_email_builds_and_sends_html(monkeypatch):
    _FakeSMTP.sent = []
    monkeypatch.setattr(notifiers_mod.smtplib, "SMTP", _FakeSMTP)

    notifier = EmailNotifier(
        smtp_host="smtp.test",
        smtp_port=587,
        sender_email="ci@test.dev",
        recipients=["dev@test.dev", "qa@test.dev"],
        password="secret",
    )
    ok = notifier.send(_summary(), title="Build 42")
    assert ok is True

    assert len(_FakeSMTP.sent) == 1
    msg: Message = _FakeSMTP.sent[0]
    assert msg["Subject"] == "Build 42"
    assert msg["From"] == "ci@test.dev"
    assert msg["To"] == "dev@test.dev, qa@test.dev"
    html = msg.get_payload()[0].get_payload()
    assert "Total Tests" in html
    assert "Pass Rate" in html


def test_email_html_has_real_values_not_placeholders(monkeypatch):
    # Bug 2: html_body was a plain (non-f) string, so emails shipped literal
    # "{summary.total}" / "{title}" / "{status_color}" placeholders, and
    # status_color was commented out (undefined).
    _FakeSMTP.sent = []
    monkeypatch.setattr(notifiers_mod.smtplib, "SMTP", _FakeSMTP)

    notifier = EmailNotifier(
        smtp_host="smtp.test",
        smtp_port=587,
        sender_email="ci@test.dev",
        recipients=["dev@test.dev"],
    )
    ok = notifier.send(
        _summary(total=42, passed=40, failed=2, pass_rate=95.2, report_url="https://report.test/7"),
        title="Nightly Build",
    )
    assert ok is True

    html = _FakeSMTP.sent[0].get_payload()[0].get_payload()

    # No literal template placeholders survive.
    for placeholder in ("{summary.total}", "{title}", "{status_color}", "{summary.report_url}", "{{"):
        assert placeholder not in html

    # Real interpolated values are present.
    assert ">42<" in html  # summary.total
    assert "Nightly Build" in html  # title
    assert "95.2%" in html  # pass_rate
    assert "#28a745" in html  # status_color for a healthy run (>= 80%)
    assert "https://report.test/7" in html  # report link


def test_email_status_color_red_for_low_pass_rate(monkeypatch):
    _FakeSMTP.sent = []
    monkeypatch.setattr(notifiers_mod.smtplib, "SMTP", _FakeSMTP)
    notifier = EmailNotifier("smtp.test", 587, "ci@test.dev", ["dev@test.dev"])
    notifier.send(_summary(passed=1, failed=9, pass_rate=10.0), title="Bad Run")
    html = _FakeSMTP.sent[0].get_payload()[0].get_payload()
    # Header background uses the failure color.
    assert "background-color: #dc3545" in html


def test_email_returns_false_on_smtp_error(monkeypatch):
    def boom(host, port):
        raise smtplib.SMTPException("no server")

    monkeypatch.setattr(notifiers_mod.smtplib, "SMTP", boom)
    notifier = EmailNotifier("smtp.test", 25, "ci@test.dev", ["a@test.dev"])
    assert notifier.send(_summary()) is False


# --- NotificationManager -----------------------------------------------------


def test_manager_fans_out_and_reports_per_channel():
    class _Always(Notifier):
        def __init__(self, value):
            self.value = value
            self.received = None

        def send(self, summary, title="Test Results"):
            self.received = (summary, title)
            return self.value

    ok = _Always(True)
    bad = _Always(False)
    mgr = NotificationManager()
    mgr.add_notifier(ok)
    mgr.add_notifier(bad)

    summary = _summary()
    results = mgr.send_all(summary, title="Release")
    assert results == {"_Always": False}  # same class name; last write wins
    assert ok.received == (summary, "Release")
    assert bad.received == (summary, "Release")


def test_manager_empty_returns_empty():
    assert NotificationManager().send_all(_summary()) == {}


@pytest.mark.parametrize(
    "rate,expected",
    [(96.0, "#36a64f"), (90.0, "#ff9900"), (50.0, "#d00000")],
)
def test_slack_color_boundaries(monkeypatch, rate, expected):
    post = _CapturingPost()
    monkeypatch.setattr(notifiers_mod.requests, "post", post)
    SlackNotifier("u").send(_summary(pass_rate=rate))
    assert post.last["json"]["attachments"][0]["color"] == expected
