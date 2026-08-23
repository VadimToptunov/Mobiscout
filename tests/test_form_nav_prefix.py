"""Review #3: the fuzz/negative form-case builders must reach a form through the shared
gate/probe/auth-aware nav prefix — never by replaying a probe edge as a tap or walking
through a login screen without credentials."""

from framework.crawler.app_crawler import parse_screen
from framework.crawler.graph import fuzz_form_cases, negative_form_cases
from framework.crawler.models import CrawlResult, Transition

APP = "com.example.app"


def _btn(text, rid):
    return (
        f'<node class="android.widget.Button" resource-id="{rid}" text="{text}" content-desc="" '
        f'clickable="true" bounds="[0,0][100,40]"/>'
    )


def _field(rid, desc):
    return (
        f'<node class="android.widget.EditText" resource-id="{rid}" text="" content-desc="{desc}" '
        f'clickable="true" bounds="[0,50][200,90]"/>'
    )


def _screen(*nodes):
    return parse_screen('<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>")


def _all_steps(cases):
    return [s for c in cases for s in c.steps]


def test_probe_edge_is_not_replayed_as_a_navigation_tap():
    # entry reaches the form by BOTH a probe edge (invalid-data submit) and a real tap.
    # The nav prefix must use the real element, never the probe one.
    entry = _screen(_btn("Real Nav", "id/real"), _btn("Probe", "id/probe"))
    form = _screen(_field("id/email", "Email"), _btn("Save", "id/save"))
    result = CrawlResult(
        screens={entry.fingerprint: entry, form.fingerprint: form},
        transitions=[
            Transition(entry.fingerprint, entry.elements[1], form.fingerprint, kind="probe"),
            Transition(entry.fingerprint, entry.elements[0], form.fingerprint, kind="tap"),
        ],
    )
    cases = fuzz_form_cases(result, APP)
    assert cases, "expected fuzz cases for the reachable form"
    locators = [s.selector.value for s in _all_steps(cases) if s.selector is not None]
    assert "id/real" in locators  # the real nav tap is used
    assert "id/probe" not in locators  # the probe edge is never replayed as a tap


def test_gated_form_prepends_auth_and_does_not_tap_the_gate():
    # The form is behind a login gate. The generated case must reach it via the auth prefix
    # (from auth_sequence), NOT by tapping the login button as if it were plain navigation.
    login = _screen(_btn("Sign in", "id/signin"))
    form = _screen(_field("id/amount", "Amount"), _btn("Confirm", "id/confirm"))
    result = CrawlResult(
        screens={login.fingerprint: login, form.fingerprint: form},
        transitions=[Transition(login.fingerprint, login.elements[0], form.fingerprint, kind="gate")],
        gated={form.fingerprint},
        auth_sequence=[{"type": "login", "username": "u", "password": "p", "submit": "Sign in"}],
    )
    cases = negative_form_cases(result, APP)
    assert cases, "expected a negative case for the gated form"
    steps = cases[0].steps
    locators = [s.selector.value for s in steps if s.selector is not None]
    # The synthetic gate element is never tapped as navigation...
    assert "id/signin" not in locators
    # ...and the form's own controls are exercised (reached past the gate).
    assert "id/confirm" in locators
    # An auth step (typing credentials) precedes the form interaction.
    from framework.codegen.ir import ActionType

    assert any(s.action is ActionType.TYPE for s in steps)
