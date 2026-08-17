"""Gated-screen nav re-rooting (device-free): a screen behind a gate navigates
from the post-auth home (which the prepended auth steps reach), not by re-tapping
from the launcher through the synthetic gate hop."""

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
    return CrawlResult(
        screens={login.fingerprint: login, home.fingerprint: home, transfer.fingerprint: transfer},
        transitions=[
            (login.fingerprint, login.elements[0], home.fingerprint),  # synthetic gate crossing
            (home.fingerprint, home.elements[0], transfer.fingerprint),  # real in-app tap
        ],
        gated={home.fingerprint, transfer.fingerprint},
    ), login, home, transfer


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
