"""
TOTP fixture — generate valid 2FA codes so tests can pass a TOTP/authenticator
gate instead of stopping at it.

A TOTP secret (the base32 string behind the authenticator QR / "manual entry
key") is a test fixture: given it, the current 6-digit code is computable with no
device and no human. RFC 6238 / RFC 4226.

    from framework.fixtures.totp import totp
    driver.find_element(...).send_keys(totp("JBSWY3DPEHPK3PXP"))
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from typing import Optional

_ALGORITHMS = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}


def _b32decode(secret: str) -> bytes:
    # Authenticator keys are base32, case-insensitive, often unpadded and spaced.
    cleaned = secret.replace(" ", "").replace("-", "").upper()
    padding = "=" * (-len(cleaned) % 8)
    return base64.b32decode(cleaned + padding)


def hotp(secret: str, counter: int, *, digits: int = 6, algorithm: str = "sha1") -> str:
    """RFC 4226 HMAC-based one-time password for an explicit counter."""
    if algorithm not in _ALGORITHMS:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    digest = hmac.new(_b32decode(secret), struct.pack(">Q", counter), _ALGORITHMS[algorithm]).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def totp(
    secret: str,
    *,
    digits: int = 6,
    period: int = 30,
    algorithm: str = "sha1",
    at: Optional[float] = None,
) -> str:
    """RFC 6238 time-based one-time password for a base32 secret.

    ``at``: Unix time to compute for (defaults to now) — pass it for
    deterministic tests. ``period``/``digits``/``algorithm`` match how the app's
    authenticator is configured (default: 30s / 6 digits / SHA-1).
    """
    now = time.time() if at is None else at
    return hotp(secret, int(now // period), digits=digits, algorithm=algorithm)


def seconds_remaining(period: int = 30, at: Optional[float] = None) -> float:
    """How long the current code stays valid — useful to wait for a fresh code
    when a test must avoid a code expiring mid-flow."""
    now = time.time() if at is None else at
    return period - (now % period)
