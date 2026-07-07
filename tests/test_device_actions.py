"""Device/system actions route to the right Appium/adb/provider call."""

import json

from framework.fixtures import device
from framework.fixtures.provider import Provider


class _FakeDriver:
    def __init__(self):
        self.log = []
        self.orientation = None

    def __getattr__(self, name):
        # Record any method call as (name, args, kwargs).
        def rec(*args, **kwargs):
            self.log.append((name, args, kwargs))
            return f"{name}:ok"

        return rec


def test_deeplink_android_vs_ios():
    d = _FakeDriver()
    device.open_deeplink(d, "app://x", "android", package="com.x")
    assert d.log[-1] == ("execute_script", ("mobile: deepLink", {"url": "app://x", "package": "com.x"}), {})
    d2 = _FakeDriver()
    device.open_deeplink(d2, "app://x", "ios")
    assert d2.log[-1] == ("get", ("app://x",), {})


def test_set_network_local_bitmask_and_browserstack_profile():
    d = _FakeDriver()
    device.set_network(d, "airplane", Provider.LOCAL)
    assert d.log[-1] == ("set_network_connection", (1,), {})
    b = _FakeDriver()
    device.set_network(b, "off", Provider.BROWSERSTACK)
    payload = json.loads(b.log[-1][1][0].split("browserstack_executor:", 1)[1])
    assert payload == {"action": "networkProfile", "arguments": {"profile": "no-network"}}


def test_location_orientation_clipboard():
    d = _FakeDriver()
    device.set_location(d, 51.5, -0.12)
    assert d.log[-1] == ("set_location", (51.5, -0.12, 0.0), {})
    device.set_orientation(d, "landscape")
    assert d.orientation == "LANDSCAPE"
    device.set_clipboard(d, "hello")
    assert d.log[-1] == ("set_clipboard_text", ("hello",), {})


def test_lifecycle_and_keys():
    d = _FakeDriver()
    device.background_app(d, 5)
    assert d.log[-1] == ("background_app", (5,), {})
    device.terminate_app(d, "com.x")
    assert d.log[-1] == ("terminate_app", ("com.x",), {})
    device.press_key(d, "BACK")
    assert d.log[-1] == ("press_keycode", (4,), {})
    device.long_press(d, 10, 20, 800)
    assert d.log[-1] == ("execute_script", ("mobile: longClickGesture", {"x": 10, "y": 20, "duration": 800}), {})


def test_grant_permission_adb_command():
    assert device.grant_permission("com.x", "android.permission.CAMERA", serial="emulator-5554") == [
        "adb",
        "-s",
        "emulator-5554",
        "shell",
        "pm",
        "grant",
        "com.x",
        "android.permission.CAMERA",
    ]
