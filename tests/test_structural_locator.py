"""Positional last-resort locator (device-free): a label-less clickable (icon /
image button with no id/text/desc) still gets a locator so it stays tappable,
instead of being dropped from the generated tests."""

from framework.codegen.ir import SelectorStrategy
from framework.crawler.app_crawler import parse_screen
from framework.crawler.to_codegen import selector_for


def _screen(*nodes):
    return parse_screen('<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>")


def _icon(cls, bounds, clickable=True):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="{cls}" resource-id="" text="" content-desc="" '
        f'clickable="{"true" if clickable else "false"}" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def test_labelless_clickables_get_positional_locators():
    scr = _screen(
        _icon("android.widget.ImageButton", (0, 0, 50, 50)),
        _icon("android.widget.ImageButton", (50, 0, 100, 50)),
    )
    icons = [e for e in scr.elements if e.class_name == "android.widget.ImageButton"]
    s0 = selector_for(icons[0], scr.elements, "android")
    s1 = selector_for(icons[1], scr.elements, "android")
    assert s0.strategy == SelectorStrategy.XPATH and s0.value == "(//android.widget.ImageButton)[1]"
    assert s1.value == "(//android.widget.ImageButton)[2]"
    assert s0.score == 0.3  # flagged fragile — never good enough to assert on


def test_labelled_element_prefers_its_real_locator():
    scr = parse_screen(
        '<hierarchy rotation="0">'
        '<node class="android.widget.Button" resource-id="id/ok" text="OK" content-desc="" '
        'clickable="true" bounds="[0,0][50,50]"/></hierarchy>'
    )
    sel = selector_for(scr.elements[0], scr.elements, "android")
    assert sel.strategy != SelectorStrategy.XPATH  # id, not positional


def test_ios_positional_uses_full_type():
    # iOS class_name has the XCUIElementType prefix stripped by the parser; the
    # positional xpath must put it back — and count only visible nodes, since that is
    # what the parser kept (see test_ios_positional_index_skips_invisible_nodes).
    scr = parse_screen(
        '<AppiumAUT><XCUIElementTypeButton name="" label="" value="" visible="true" '
        'x="0" y="0" width="40" height="40"/></AppiumAUT>'
    )
    btn = next(e for e in scr.elements if e.class_name == "Button")
    sel = selector_for(btn, scr.elements, "ios")
    assert sel is not None and sel.value == '(//XCUIElementTypeButton[@visible="true"])[1]'


def test_ios_positional_index_skips_invisible_nodes():
    # The parser drops visible="false" nodes but the XCUITest source the xpath runs
    # against still holds them, so an unscoped (//Button)[1] would resolve to the
    # invisible one — a tap on the wrong element.
    scr = parse_screen(
        "<AppiumAUT>"
        '<XCUIElementTypeButton name="" label="" value="" visible="false" x="0" y="0" width="40" height="40"/>'
        '<XCUIElementTypeButton name="" label="" value="" visible="true" x="0" y="50" width="40" height="40"/>'
        "</AppiumAUT>"
    )
    btn = next(e for e in scr.elements if e.class_name == "Button")
    sel = selector_for(btn, scr.elements, "ios")
    assert sel is not None and sel.value == '(//XCUIElementTypeButton[@visible="true"])[1]'


def test_android_positional_is_scoped_to_the_app_package():
    # A system-UI / IME node of the same class ahead of the target would shift a
    # document-wide index, so the xpath is scoped to the app's package.
    scr = _screen(
        '<node class="android.widget.ImageButton" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[0,0][50,50]" package="com.android.systemui"/>',
        '<node class="android.widget.ImageButton" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[50,0][100,50]" package="com.example.app"/>',
    )
    owned = [e for e in scr.elements if e.package == "com.example.app"]
    sel = selector_for(owned[0], owned, "android")
    assert sel is not None and sel.value == "(//android.widget.ImageButton[@package='com.example.app'])[1]"


def test_no_siblings_labelless_stays_none():
    scr = _screen(_icon("android.widget.ImageButton", (0, 0, 50, 50)))
    assert selector_for(scr.elements[0], None, "android") is None
