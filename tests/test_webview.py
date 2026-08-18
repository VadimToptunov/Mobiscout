"""Device-free tests for general WebView (Mode 2) support.

Two layers:
  * the pure XML synthesis (`build_web_screen`) round-trips through the real
    `parse_screen`, proving web DOM becomes first-class crawl elements; and
  * `web_snapshot` / `click_web` / `type_web` drive a fake Appium session,
    proving the context switch + DOM mapping without a device.
"""

from __future__ import annotations

from framework.crawler import webview
from framework.crawler.parse import parse_screen
from framework.crawler.waypoints import _is_input

# A tiny login DOM: username + password inputs and a submit button.
_NODES = [
    {
        "i": 0,
        "tag": "input",
        "type": "text",
        "text": "username",
        "name": "username",
        "x": 20,
        "y": 100,
        "w": 280,
        "h": 44,
    },
    {
        "i": 1,
        "tag": "input",
        "type": "password",
        "text": "password",
        "name": "password",
        "x": 20,
        "y": 160,
        "w": 280,
        "h": 44,
    },
    {"i": 5, "tag": "button", "type": "submit", "text": "Log in", "name": "", "x": 20, "y": 220, "w": 280, "h": 48},
    {"i": 9, "tag": "a", "type": "", "text": "Forgot password?", "name": "", "x": 20, "y": 290, "w": 160, "h": 20},
]


def test_build_web_screen_round_trips_through_parser():
    xml, centers = webview.build_web_screen(_NODES)
    screen = parse_screen(xml)
    # Every visible interactive node becomes a clickable element.
    assert len(screen.elements) == 4
    assert all(e.clickable for e in screen.elements)
    by_text = {e.text: e for e in screen.elements}
    # Inputs carry EditText semantics so waypoints recognise them; the password
    # field is flagged; the anchor/button are not inputs.
    assert _is_input(by_text["username"])
    assert _is_input(by_text["password"])
    assert by_text["password"].password is True
    assert not _is_input(by_text["Log in"])
    assert not _is_input(by_text["Forgot password?"])


def test_centers_map_matches_element_center():
    # A tap on element.center must resolve back to the right DOM node.
    xml, centers = webview.build_web_screen(_NODES)
    screen = parse_screen(xml)
    for e in screen.elements:
        assert e.center in centers, f"{e.text} center {e.center} not mapped"


class _FakeActive:
    def __init__(self, sink):
        self._sink = sink

    def send_keys(self, text):
        self._sink.append(("active", text))


class _FakeSwitch:
    def __init__(self, drv):
        self._drv = drv

    def context(self, name):
        self._drv.context = name
        self._drv.switches.append(name)

    @property
    def active_element(self):
        return _FakeActive(self._drv.typed)


class _FakeEl:
    def __init__(self, drv, sel):
        self._drv = drv
        self._sel = sel
        # data-mtr-id="1" is the password input in _NODES.
        self.tag_name = "input" if sel in ('[data-mtr-id="0"]', '[data-mtr-id="1"]') else "button"

    def click(self):
        self._drv.clicks.append(self._sel)

    def send_keys(self, text):
        self._drv.typed.append((self._sel, text))


class _FakeDriver:
    """Minimal Appium-session stand-in: a native + a webview context, an
    execute_script that returns the login DOM, and click/send_keys recorders."""

    def __init__(self):
        self.context = "NATIVE_APP"
        self.contexts = ["NATIVE_APP", "WEBVIEW_test"]
        self.switches = []
        self.clicks = []
        self.typed = []
        self.switch_to = _FakeSwitch(self)

    def execute_script(self, script, *args):
        return _NODES

    def find_element(self, by, sel):
        return _FakeEl(self, sel)


def test_web_snapshot_detects_and_returns_to_native():
    d = _FakeDriver()
    snap = webview.web_snapshot(d)
    assert snap is not None
    assert snap["ctx"] == "WEBVIEW_test"
    assert d.context == "NATIVE_APP"  # left native after reading
    # The submit button (data-mtr-id 5) is reachable via its center.
    screen = parse_screen(snap["xml"])
    login = next(e for e in screen.elements if e.text == "Log in")
    assert snap["centers"][login.center] == 5


def test_click_and_type_route_through_dom():
    d = _FakeDriver()
    snap = webview.web_snapshot(d)
    user = next(e for e in parse_screen(snap["xml"]).elements if e.text == "username")
    # Tap the username input -> clicks the DOM node, remembers it as focused.
    x, y = user.center
    assert webview.click_web(d, snap, x, y) is True
    assert d.clicks == ['[data-mtr-id="0"]']
    assert snap["focused"] == 0
    assert d.context == "NATIVE_APP"  # returned to native after the click
    # Type -> send_keys to the focused input in the web context.
    assert webview.type_web(d, snap, "demo") is True
    assert ('[data-mtr-id="0"]', "demo") in d.typed


def test_click_web_misses_off_target_point():
    d = _FakeDriver()
    snap = webview.web_snapshot(d)
    assert webview.click_web(d, snap, 9999, 9999) is False
    assert d.clicks == []


def test_no_webview_context_returns_none():
    d = _FakeDriver()
    d.contexts = ["NATIVE_APP"]
    assert webview.web_snapshot(d) is None
