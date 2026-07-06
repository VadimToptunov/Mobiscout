"""
Device & system actions — the automatable surface beyond tap/type/swipe.

A real test needs to change conditions and drive system-level actions, not just
poke the UI: jump via a deep link, flip the network, mock a location, rotate,
grant a permission, background the app, read the clipboard, press a hardware key.
These are the scriptable ones (Appium / adb / provider executors), gathered into
one discoverable, provider-aware place so a test — or a crawler waypoint — can use
them.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional

from framework.fixtures.provider import Provider

# Common Android keycodes (press_key).
KEY = {"BACK": 4, "HOME": 3, "ENTER": 66, "TAB": 61, "SEARCH": 84, "APP_SWITCH": 187, "DEL": 67}

# Android ConnectivityManager bitmask for set_network (local).
_NET = {"airplane": 1, "wifi": 2, "data": 4, "all": 6, "off": 0}


# ---- navigation / lifecycle -------------------------------------------------
def open_deeplink(driver, url: str, platform: str = "android", package: Optional[str] = None) -> Any:
    """Jump straight to a screen via a deep link / URL scheme — the fastest way
    past gates the DFS can't tap through."""
    if platform == "ios":
        return driver.get(url)
    return driver.execute_script("mobile: deepLink", {"url": url, "package": package})


def background_app(driver, seconds: float = -1) -> Any:
    """Send the app to the background for ``seconds`` (-1 = leave it there)."""
    return driver.background_app(seconds)


def terminate_app(driver, app_id: str) -> Any:
    return driver.terminate_app(app_id)


def activate_app(driver, app_id: str) -> Any:
    return driver.activate_app(app_id)


# ---- device conditions ------------------------------------------------------
def set_location(driver, latitude: float, longitude: float, altitude: float = 0.0) -> Any:
    """Mock the GPS location (point). Feed a sequence for a route."""
    return driver.set_location(latitude, longitude, altitude)


def set_orientation(driver, orientation: str = "LANDSCAPE") -> None:
    driver.orientation = orientation.upper()


def set_clipboard(driver, text: str) -> Any:
    return driver.set_clipboard_text(text)


def get_clipboard(driver) -> Any:
    return driver.get_clipboard_text()


def set_network(driver, mode: str, provider: Provider = Provider.LOCAL) -> Any:
    """Change connectivity — offline / airplane / wifi / data — to test degraded
    conditions. BrowserStack uses named network profiles; local uses the Android
    connectivity bitmask."""
    if provider is Provider.BROWSERSTACK:
        profile = {"off": "no-network", "airplane": "airplane-mode"}.get(mode, mode)
        payload = json.dumps({"action": "networkProfile", "arguments": {"profile": profile}})
        return driver.execute_script(f"browserstack_executor: {payload}")
    return driver.set_network_connection(_NET.get(mode, 6))


# ---- system / input ---------------------------------------------------------
def grant_permission(package: str, permission: str, serial: Optional[str] = None, adb: str = "adb") -> List[str]:
    """adb command to grant a runtime permission (skip the permission prompt)."""
    dev = ["-s", serial] if serial else []
    return [adb, *dev, "shell", "pm", "grant", package, permission]


def press_key(driver, key: str) -> Any:
    """Press a hardware/soft key by name (BACK/HOME/ENTER/…) on Android."""
    return driver.press_keycode(KEY.get(key.upper(), 0) if not key.isdigit() else int(key))


def hide_keyboard(driver) -> Any:
    return driver.hide_keyboard()


def open_notifications(driver) -> Any:
    """Pull down the notification shade (Android)."""
    return driver.open_notifications()


def long_press(driver, x: int, y: int, duration_ms: int = 1000) -> Any:
    """Long-press at a point (Android gesture)."""
    return driver.execute_script("mobile: longClickGesture", {"x": x, "y": y, "duration": duration_ms})


def scroll_to_text(driver, text: str) -> Any:
    """Scroll a scrollable until an element with ``text`` is on screen (Android
    UiScrollable)."""
    selector = (
        "new UiScrollable(new UiSelector().scrollable(true))"
        f'.scrollIntoView(new UiSelector().textContains("{text}"))'
    )
    from appium.webdriver.common.appiumby import AppiumBy

    return driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, selector)
