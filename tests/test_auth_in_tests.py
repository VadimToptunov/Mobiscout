"""Auth in generated tests (device-free): waypoints become IR auth steps, and the
generated per-screen cases for behind-the-gate screens get them prepended — so a
test can reach the screen instead of stalling on login."""

from framework.codegen.ir import ActionType
from framework.crawler.app_crawler import parse_screen
from framework.crawler.models import CrawlResult
from framework.crawler.to_codegen import build_test_model, waypoints_to_steps

APP = "com.example.app"

_WP = [{"when": {"has_input": True}, "action": "fill",
        "data": {"fields": {"user": "demo", "password": "pw"}, "submit": "Sign in"}}]


def test_waypoints_to_steps_fill_makes_type_and_tap():
    steps = waypoints_to_steps(_WP, "android")
    typed = [s.text for s in steps if s.action == ActionType.TYPE]
    assert typed == ["demo", "pw"]  # a TYPE per field, in order
    assert steps[-1].action == ActionType.TAP  # then tap the submit


def test_no_waypoints_is_empty():
    assert waypoints_to_steps(None, "android") == []
    assert waypoints_to_steps([], "ios") == []


def _btn(text, rid, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.Button" resource-id="{rid}" text="{text}" content-desc="" '
        f'clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _screen(*nodes):
    return parse_screen('<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>")


def _build_two_screen_result(gated):
    login = _screen(_btn("Sign in", "id/signin", (0, 0, 200, 50)))
    home = _screen(_btn("Accounts", "id/accounts", (0, 0, 200, 50)))
    login_fp, home_fp = login.fingerprint, home.fingerprint
    signin = login.elements[0]
    return CrawlResult(
        screens={login_fp: login, home_fp: home},
        transitions=[(login_fp, signin, home_fp)],
        gated=({home_fp} if gated else set()),
    ), home_fp, login_fp


def test_auth_prepended_only_to_gated_screen():
    result, home_fp, login_fp = _build_two_screen_result(gated=True)
    model = build_test_model(result, APP, waypoints=_WP)

    def _has_auth(case):
        return any(s.action == ActionType.TYPE and s.text == "demo" for s in case.steps)

    state_cases = [c for c in model.cases if c.name.endswith("shows_expected_controls")]
    with_auth = [c for c in state_cases if _has_auth(c)]
    without_auth = [c for c in state_cases if not _has_auth(c)]
    assert len(with_auth) == 1  # only the gated (home) screen gets auth
    assert len(without_auth) == 1  # the login screen itself does not
    # The auth runs right after launch, before the screen's own steps.
    home_case = with_auth[0]
    assert home_case.steps[0].action == ActionType.LAUNCH
    assert home_case.steps[1].action == ActionType.TYPE


def test_no_gated_screens_means_no_auth_anywhere():
    result, _, _ = _build_two_screen_result(gated=False)
    model = build_test_model(result, APP, waypoints=_WP)
    assert all(
        not any(s.action == ActionType.TYPE and s.text == "demo" for s in c.steps) for c in model.cases
    )
