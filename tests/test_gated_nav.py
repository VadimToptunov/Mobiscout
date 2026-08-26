"""Gated-screen nav re-rooting (device-free): a screen behind a gate navigates
from the post-auth home (which the prepended auth steps reach), not by re-tapping
from the launcher through the synthetic gate hop."""

from framework.codegen.ir import ActionType, Step
from framework.crawler.app_crawler import parse_screen
from framework.crawler.graph import navigation_steps
from framework.crawler.models import CrawlResult

APP = "com.example.app"


def _btn(text, rid, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.Button" resource-id="{rid}" text="{text}" content-desc="" '
        f'clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _screen(*nodes):
    return parse_screen('<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>")


def _result():
    login = _screen(_btn("Sign in", "id/signin", (0, 0, 100, 40)))
    home = _screen(_btn("Send", "id/send", (0, 0, 100, 40)))
    transfer = _screen(_btn("Confirm", "id/confirm", (0, 0, 100, 40)))
    return (
        CrawlResult(
            screens={login.fingerprint: login, home.fingerprint: home, transfer.fingerprint: transfer},
            transitions=[
                (login.fingerprint, login.elements[0], home.fingerprint),  # synthetic gate crossing
                (home.fingerprint, home.elements[0], transfer.fingerprint),  # real in-app tap
            ],
            gated={home.fingerprint, transfer.fingerprint},
        ),
        login,
        home,
        transfer,
    )


def test_gated_home_has_no_in_app_nav():
    result, _login, home, _transfer = _result()
    nav = navigation_steps(result, APP)
    # Auth lands the test on home, so its nav prefix is empty (no re-tap from launch).
    assert nav.get(home.fingerprint) == []


def test_gated_deep_screen_navigates_from_home_only():
    result, _login, _home, transfer = _result()
    nav = navigation_steps(result, APP)
    steps = nav[transfer.fingerprint]
    # Just the home->transfer hop, not the login->home gate hop as well.
    assert len(steps) == 1
    assert "Send" in steps[0].description


def test_non_gated_nav_unchanged():
    # No gated screens => paths are rooted at the launcher as before.
    result, _login, _home, transfer = _result()
    result.gated = set()
    nav = navigation_steps(result, APP)
    assert len(nav[transfer.fingerprint]) == 2  # login->home, home->transfer


def test_mid_crawl_gate_keeps_the_hops_that_reach_the_login():
    # The gate is NOT the launch screen: entry --tap Profile--> login --gate--> account.
    # The hops that reach the login form must survive, with the auth steps after them —
    # trimming them typed the credentials into the entry screen, which has no such fields.
    entry = _screen(_btn("Profile", "id/profile", (0, 0, 100, 40)))
    login = _screen(_btn("Log in", "id/login", (0, 0, 100, 40)))
    account = _screen(_btn("Statements", "id/statements", (0, 0, 100, 40)))
    result = CrawlResult(
        screens={entry.fingerprint: entry, login.fingerprint: login, account.fingerprint: account},
        transitions=[
            (entry.fingerprint, entry.elements[0], login.fingerprint),  # real tap
            (login.fingerprint, login.elements[0], account.fingerprint),  # synthetic gate crossing
        ],
        gated={account.fingerprint},
    )
    auth = [Step(ActionType.TYPE, text="demo", description="Enter user")]
    steps = navigation_steps(result, APP, auth_steps=auth)[account.fingerprint]
    assert [s.description for s in steps] == ["Navigate: tap Profile", "Enter user"]
