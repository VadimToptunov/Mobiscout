"""`crawl --login-user` and friends: passing a sign-in gate from the CLI.

A gated app is the normal case in this tool's target niche, and without credentials a crawl
of one yields exactly its sign-in screen. The daemon/IDE path already accepted `waypoints`;
the CLI had no way to express them at all.

The type matters more than it looks: AppCrawler reads `.when`/`.action` off a Waypoint, and
handing it the config dicts the daemon accepts ends the crawl on its first screen — silently,
because a dict simply has no such attributes. Measured against a live gated app: dicts gave
1 screen / 0 transitions, Waypoint objects gave 4 screens / 5 transitions.
"""

import os

from framework.cli.crawl_commands import _gate_waypoints
from framework.crawler.waypoints import Waypoint, matches
from framework.crawler.models import CrawlElement, CrawlScreen


def _login_screen() -> CrawlScreen:
    return CrawlScreen(
        "fp",
        [
            CrawlElement("id/user", "", "", "android.widget.EditText", True, (0, 0, 200, 40)),
            CrawlElement("id/pass", "", "", "android.widget.EditText", True, (0, 50, 200, 90)),
            CrawlElement("id/go", "Log in", "", "android.widget.Button", True, (0, 100, 200, 140)),
        ],
        platform="android",
    )


def test_no_credentials_means_no_gate():
    assert _gate_waypoints(None, None, "log in", None, "verify") == []


def test_waypoints_are_objects_the_crawler_can_read():
    # The whole point: AppCrawler reads attributes, so dicts would end the crawl at once.
    gates = _gate_waypoints("demo", "pw", "Log in", None, "verify")
    assert [type(w) for w in gates] == [Waypoint]
    assert matches(gates[0], _login_screen()), "the login waypoint must fire on a screen with inputs"


def test_a_one_time_code_is_a_second_gate_after_the_password():
    gates = _gate_waypoints("demo", "pw", "Log in", "JBSWY3DPEHPK3PXP", "Verify")
    assert [w.action for w in gates] == ["fill", "totp"]  # order is the passing order
    assert gates[1].data["secret"] == "JBSWY3DPEHPK3PXP"
    assert gates[1].data["submit"] == "Verify"


def test_secrets_can_come_from_the_environment(monkeypatch):
    # So they need not appear in a command line, and from there in shell history or a CI log.
    monkeypatch.setenv("MOBISCOUT_LOGIN_USER", "env-user")
    monkeypatch.setenv("MOBISCOUT_LOGIN_PASSWORD", "env-pass")
    monkeypatch.setenv("MOBISCOUT_OTP_SECRET", "ENVSECRET")
    gates = _gate_waypoints(None, None, "log in", None, "verify")
    assert gates[0].data["fields"] == {"user": "env-user", "password": "env-pass"}
    assert gates[1].data["secret"] == "ENVSECRET"


def test_an_explicit_flag_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_LOGIN_USER", "env-user")
    assert _gate_waypoints("flag-user", "pw", "log in", None, "verify")[0].data["fields"]["user"] == "flag-user"


def test_submit_labels_fall_back_to_sensible_defaults():
    gates = _gate_waypoints("demo", "pw", "", "SECRET", "")
    assert gates[0].data["submit"] == "log in"
    assert gates[1].data["submit"] == "verify"
