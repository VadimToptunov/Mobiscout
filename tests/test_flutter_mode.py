"""Device-free tests for Flutter integration-server support ("Route B").

The pure XML synthesis (`build_flutter_screen`) round-trips through the real
`parse_screen`, proving an enumerated Flutter widget tree becomes first-class crawl
elements with stable locators (a `ValueKey` lands in the locator field, a semantics
label in content-desc) — with no change to the crawler or parser.
"""

from __future__ import annotations

from framework.crawler import flutter_mode
from framework.crawler.parse import parse_screen
from framework.crawler.waypoints import _is_input

# A tiny login screen: a keyed username field, an obscured password field, a labelled
# submit button, and a plain-text link with neither key nor label.
_NODES = [
    {
        "i": 0,
        "type": "TextField",
        "key": "login.username",
        "label": "Username",
        "text": "",
        "editable": True,
        "x": 20,
        "y": 100,
        "w": 280,
        "h": 44,
    },
    {
        "i": 1,
        "type": "TextField",
        "key": "login.password",
        "label": "Password",
        "text": "",
        "editable": True,
        "password": True,
        "x": 20,
        "y": 160,
        "w": 280,
        "h": 44,
    },
    {
        "i": 5,
        "type": "ElevatedButton",
        "key": "login.submit",
        "label": "",
        "text": "Log in",
        "x": 20,
        "y": 220,
        "w": 280,
        "h": 48,
    },
    {"i": 9, "type": "Text", "key": "", "label": "", "text": "Forgot password?", "x": 20, "y": 290, "w": 160, "h": 20},
]


def test_build_flutter_screen_round_trips_through_parser():
    xml, _ = flutter_mode.build_flutter_screen(_NODES)
    screen = parse_screen(xml)
    # The integration server serves the real widget tree, so the screen is tagged
    # flutter via the marker (not the FlutterView-canvas fallback).
    assert screen.toolkit == "flutter"
    assert len(screen.elements) == 4
    assert all(e.clickable for e in screen.elements)

    by_text = {e.text: e for e in screen.elements if e.text}
    # The ValueKey is the stable locator -> resource_id, so codegen can emit
    # find.byValueKey instead of a positional tap.
    submit = by_text["Log in"]
    assert submit.resource_id == "login.submit"
    assert not _is_input(submit)

    # Inputs carry TextField semantics so waypoints recognise them; the password
    # field is flagged; its semantics label rides in content_desc.
    by_key = {e.resource_id: e for e in screen.elements}
    username = by_key["login.username"]
    password = by_key["login.password"]
    assert _is_input(username)
    assert _is_input(password)
    assert username.content_desc == "Username"
    assert password.password is True

    # A key-less, label-less widget still crawls (by text), it just has no id handle.
    forgot = by_text["Forgot password?"]
    assert forgot.resource_id == ""
    assert not _is_input(forgot)


def test_centers_map_matches_element_center():
    # A tap on element.center must resolve back to the right widget id.
    xml, centers = flutter_mode.build_flutter_screen(_NODES)
    screen = parse_screen(xml)
    for e in screen.elements:
        assert e.center in centers, f"{e.label} center {e.center} not mapped"


def test_degenerate_rects_dropped_and_empty_has_no_centers():
    nodes = [{"i": 0, "type": "Text", "text": "zero", "x": 10, "y": 10, "w": 0, "h": 20}]
    xml, centers = flutter_mode.build_flutter_screen(nodes)
    assert centers == {}
    assert parse_screen(xml).elements == []
