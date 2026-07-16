"""iOS (XCUITest) parsing must drop off-screen elements. Found live on a SwiftUI
app (ChaosBank) whose auth gate covered the UI: XCUITest still reports the hidden
Home/tab buttons with visible="false", which flooded the inventory with 100+
phantom elements and made the crawler waste steps tapping non-hittable controls."""

from framework.crawler.app_crawler import parse_screen

_IOS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="ChaosBank" x="0" y="0" width="393" height="852" visible="true">
  <XCUIElementTypeButton type="XCUIElementTypeButton" name="auth.gate" label="Log in" x="20" y="700" width="353" height="50" enabled="true" visible="true"/>
  <XCUIElementTypeButton type="XCUIElementTypeButton" name="Home" label="Home" x="10" y="800" width="80" height="40" enabled="true" visible="false"/>
  <XCUIElementTypeButton type="XCUIElementTypeButton" name="Markets" label="Markets" x="100" y="800" width="80" height="40" enabled="true" visible="false"/>
  <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="title" label="Welcome" x="20" y="100" width="200" height="30" visible="true"/>
</XCUIElementTypeApplication>"""


def test_hidden_ios_elements_are_dropped():
    screen = parse_screen(_IOS_XML)
    names = {e.content_desc for e in screen.elements}
    # The visible auth gate + the visible title survive; the covered Home/Markets
    # tabs (visible="false") do not.
    assert "auth.gate" in names
    assert "title" in names
    assert "Home" not in names and "Markets" not in names


def test_visible_ios_button_is_interactive():
    screen = parse_screen(_IOS_XML)
    gate = next(e for e in screen.elements if e.content_desc == "auth.gate")
    assert gate.clickable is True  # a visible, enabled Button is tappable
    assert screen.platform == "ios"


def test_android_parsing_unaffected_by_visible_filter():
    # The visible filter is iOS-only; Android uiautomator has no such attribute and
    # must still parse normally.
    android = (
        '<hierarchy><node class="android.widget.Button" resource-id="a:id/ok" text="OK" '
        'content-desc="" clickable="true" bounds="[0,0][100,50]" package="a"/></hierarchy>'
    )
    screen = parse_screen(android)
    assert len(screen.elements) == 1 and screen.platform == "android"
