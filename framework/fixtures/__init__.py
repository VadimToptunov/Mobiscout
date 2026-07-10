"""
Test fixtures for *gated* flows — the parts of an app a blind UI crawl can't get
through: TOTP/2FA, biometrics, QR scans, document (KYC) scans.

Each fixture provides the minimum a test (or a crawler waypoint) needs to satisfy
the gate and keep going, so an app can be tested end to end.
"""

from framework.fixtures.biometric import pass_biometric
from framework.fixtures.camera import scan_document, scan_qr
from framework.fixtures.device import (
    grant_permission,
    open_deeplink,
    press_key,
    set_location,
    set_network,
    set_orientation,
)
from framework.fixtures.provider import Provider, detect
from framework.fixtures.totp import hotp, seconds_remaining, totp

__all__ = [
    "totp",
    "hotp",
    "seconds_remaining",
    "pass_biometric",
    "scan_qr",
    "scan_document",
    "open_deeplink",
    "set_network",
    "set_location",
    "set_orientation",
    "grant_permission",
    "press_key",
    "Provider",
    "detect",
]
