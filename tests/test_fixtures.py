"""Gated-flow fixtures: TOTP against the RFC 6238 vectors, biometric helpers
produce the right driver calls / adb commands."""

import pytest

from framework.fixtures import biometric
from framework.fixtures.totp import hotp, seconds_remaining, totp

# RFC 6238 Appendix B, SHA-1, secret ASCII "12345678901234567890".
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.mark.parametrize(
    "at,expected8",
    [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"), (1234567890, "89005924")],
)
def test_totp_matches_rfc6238_vectors(at, expected8):
    assert totp(RFC_SECRET, at=at, digits=8) == expected8
    assert totp(RFC_SECRET, at=at, digits=6) == expected8[-6:]


def test_totp_defaults_to_six_digits_and_is_numeric():
    code = totp(RFC_SECRET, at=59)
    assert len(code) == 6 and code.isdigit()


def test_hotp_rfc4226_first_values():
    # RFC 4226 Appendix D expects 755224 at counter 0 for this secret.
    assert hotp(RFC_SECRET, 0) == "755224"


def test_secret_is_case_and_space_insensitive():
    assert totp("jbsw y3dp ehpk 3pxp", at=59) == totp("JBSWY3DPEHPK3PXP", at=59)


def test_seconds_remaining_within_period():
    assert seconds_remaining(period=30, at=100) == pytest.approx(20.0)


def test_android_adb_fingerprint_command():
    assert biometric.android_adb_fingerprint(2, serial="emulator-5554") == [
        "adb",
        "-s",
        "emulator-5554",
        "emu",
        "finger",
        "touch",
        "2",
    ]


class _FakeDriver:
    def __init__(self):
        self.calls = []

    def execute_script(self, name, arg):
        self.calls.append((name, arg))


def test_pass_biometric_ios_sends_match():
    d = _FakeDriver()
    biometric.pass_biometric(d, "ios", match=True)
    assert d.calls == [("mobile: sendBiometricMatch", {"type": "touchId", "match": True})]


def test_pass_biometric_android_sends_fingerprint():
    d = _FakeDriver()
    biometric.pass_biometric(d, "android", finger_id=3)
    assert d.calls == [("mobile: fingerprint", {"fingerprintId": 3})]
