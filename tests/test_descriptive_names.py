"""Descriptive test names (device-free): a screen is named after its content — a
text landmark, or (when it has none, e.g. a login form) its most salient control —
so a generated case reads like a sentence, never `test_screen_1`."""

from framework.crawler.app_crawler import parse_screen
from framework.crawler.models import CrawlResult
from framework.crawler.to_codegen import build_test_model


def _screen(*nodes):
    return parse_screen('<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>")


def _node(cls, text, rid, bounds, clickable=True):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="{cls}" resource-id="{rid}" text="{text}" content-desc="" '
        f'clickable="{"true" if clickable else "false"}" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def test_text_landmark_names_the_screen():
    scr = _screen(
        _node("android.widget.TextView", "Total balance", "", (0, 0, 200, 30), clickable=False),
        _node("android.widget.Button", "Add money", "id/add", (0, 40, 200, 80)),
    )
    model = build_test_model(CrawlResult(screens={scr.fingerprint: scr}, transitions=[]), "com.app")
    assert any("total_balance" in c.name for c in model.cases)
    assert not any(c.name.startswith("screen_") for c in model.cases)


def test_control_only_screen_named_after_its_control():
    # A login form has no static title text — name it after the button, not screen_N.
    scr = _screen(
        _node("android.widget.EditText", "Username", "id/user", (0, 0, 200, 30)),
        _node("android.widget.Button", "Sign in", "id/signin", (0, 40, 200, 80)),
    )
    model = build_test_model(CrawlResult(screens={scr.fingerprint: scr}, transitions=[]), "com.app")
    names = [c.name for c in model.cases]
    assert any(("sign_in" in n or "username" in n) for n in names), names
    assert not any(n.startswith("screen_") for n in names), names


def test_labelless_nav_named_after_destination():
    # A Compose clickable wrapper is a label-less android.view.View. The navigation
    # case must be named after where it goes, not "tapping_android_view_view".
    a = _screen(_node("android.view.View", "", "", (0, 0, 100, 50)))
    b = _screen(
        _node("android.widget.TextView", "Filters", "", (0, 0, 100, 30), clickable=False),
        _node("android.widget.Button", "Apply", "id/apply", (0, 40, 100, 80)),
    )
    result = CrawlResult(
        screens={a.fingerprint: a, b.fingerprint: b},
        transitions=[(a.fingerprint, a.elements[0], b.fingerprint)],
    )
    names = [c.name for c in build_test_model(result, "com.app").cases]
    assert not any("android_view_view" in n for n in names), names
    assert any(("navigate_to" in n or "filters" in n) for n in names), names
