"""
Biometric fixture — pass a fingerprint / Face ID prompt in an automated test.

Biometrics can't be "tapped", but every simulator/emulator can be told to emit a
matching (or non-matching) biometric event. These helpers produce the right
Appium call or adb command so a test — or the crawler, at a biometric gate — can
continue instead of stalling.

Android emulator: enrol a fingerprint once (Settings), then emit touches.
iOS simulator: enrol via Appium, then send a match / non-match.
"""

from __future__ import annotations

from typing import List, Optional


def android_adb_fingerprint(finger_id: int = 1, serial: Optional[str] = None, adb: str = "adb") -> List[str]:
    """adb command that emits a fingerprint touch on the emulator
    (``adb emu finger touch <id>``). The finger must already be enrolled."""
    base = [adb] + (["-s", serial] if serial else []) + ["emu", "finger", "touch", str(finger_id)]
    return base


def android_fingerprint(driver, finger_id: int = 1) -> None:
    """Emit a matching fingerprint via Appium (UiAutomator2 ``mobile:
    fingerprint``). The finger id must be enrolled on the emulator."""
    driver.execute_script("mobile: fingerprint", {"fingerprintId": finger_id})


def ios_enroll_biometric(driver, enrolled: bool = True) -> None:
    """Enrol (or un-enrol) Touch ID / Face ID on the iOS simulator via Appium."""
    driver.execute_script("mobile: enrollBiometric", {"isEnabled": enrolled})


def ios_biometric_match(driver, match: bool = True, biometric_type: str = "touchId") -> None:
    """Send a biometric match / non-match to the iOS simulator via Appium
    (``mobile: sendBiometricMatch``). ``biometric_type``: touchId | faceId."""
    driver.execute_script("mobile: sendBiometricMatch", {"type": biometric_type, "match": match})


def pass_biometric(driver, platform: str, *, match: bool = True, finger_id: int = 1) -> None:
    """Platform-agnostic: satisfy the biometric prompt on whichever platform the
    session is running (the one call a generated test or a crawler waypoint uses)."""
    if platform == "ios":
        ios_biometric_match(driver, match=match)
    else:
        android_fingerprint(driver, finger_id=finger_id)
