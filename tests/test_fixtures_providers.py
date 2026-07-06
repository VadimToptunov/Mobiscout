"""Provider-aware fixtures: the same gate call routes to the right mechanism for
a local emulator, BrowserStack, or a real device (and refuses the impossible)."""

import json

import pytest

from framework.fixtures import biometric, camera
from framework.fixtures.provider import Provider, RealDeviceGateError, detect


class _FakeDriver:
    def __init__(self):
        self.calls = []

    def execute_script(self, script):
        self.calls.append(script)
        return "ok"


def test_detect_browserstack_from_caps():
    assert detect({"bstack:options": {"userName": "x"}}) is Provider.BROWSERSTACK
    assert detect(server="https://hub.browserstack.com/wd/hub") is Provider.BROWSERSTACK


def test_detect_local_vs_real():
    assert detect({"appium:deviceName": "Pixel_7_API_34 emulator"}) is Provider.LOCAL
    assert detect({"appium:udid": "00008110-realdeviceudid"}) is Provider.REAL


def test_camera_injection_browserstack_executor():
    d = _FakeDriver()
    camera.scan_qr(d, "media://abc123", Provider.BROWSERSTACK)
    assert len(d.calls) == 1 and d.calls[0].startswith("browserstack_executor:")
    action = json.loads(d.calls[0].split("browserstack_executor:", 1)[1])
    assert action == {"action": "cameraImageInjection", "arguments": {"imageUrl": "media://abc123"}}


def test_document_scan_local_surfaces_intent():
    d = _FakeDriver()
    result = camera.scan_document(d, "/tmp/passport.png", Provider.LOCAL)
    assert result["action"] == "camera_image" and result["image"] == "/tmp/passport.png"
    assert d.calls == []  # local injection is not a driver script


def test_camera_injection_real_device_refused():
    with pytest.raises(RealDeviceGateError):
        camera.scan_document(_FakeDriver(), "/tmp/passport.png", Provider.REAL)


def test_biometric_browserstack_executor():
    d = _FakeDriver()
    biometric.pass_biometric(d, "android", provider=Provider.BROWSERSTACK)
    action = json.loads(d.calls[0].split("browserstack_executor:", 1)[1])
    assert action == {"action": "biometric", "arguments": {"action": "match"}}


def test_biometric_real_device_refused():
    with pytest.raises(RealDeviceGateError):
        biometric.pass_biometric(_FakeDriver(), "ios", provider=Provider.REAL)
