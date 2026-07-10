"""
Where a test runs decides *how* a gate is satisfied. The same fixture call must
work on a local emulator/simulator, on BrowserStack, and on a real device — but
the mechanism differs, and some gates simply can't be faked on a real device.

    Provider.LOCAL       adb / simctl / Appium emulator commands
    Provider.BROWSERSTACK browserstack_executor + media injection
    Provider.REAL        a physical device — biometric/camera need an in-app hook
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class Provider(str, Enum):
    LOCAL = "local"
    BROWSERSTACK = "browserstack"
    REAL = "real"


def detect(caps: Optional[Dict[str, Any]] = None, server: str = "") -> Provider:
    """Infer the provider from the Appium capabilities / server URL."""
    caps = caps or {}
    blob = f"{server} {caps}".lower()
    if "browserstack" in blob or "bstack:options" in caps or "bstack" in blob:
        return Provider.BROWSERSTACK
    # Emulator/simulator device names are the local case; anything else that is a
    # concrete udid/serial is treated as a real device.
    device = str(caps.get("appium:deviceName") or caps.get("deviceName") or "").lower()
    udid = caps.get("appium:udid") or caps.get("udid")
    if any(k in device for k in ("emulator", "simulator", "sdk_gphone", "iphone simulator")):
        return Provider.LOCAL
    if udid and "emulator-" not in str(udid):
        return Provider.REAL
    return Provider.LOCAL


class RealDeviceGateError(RuntimeError):
    """A gate that a real device can't emulate externally — it needs an in-app
    test hook (a debug build that bypasses/injects the gate)."""
