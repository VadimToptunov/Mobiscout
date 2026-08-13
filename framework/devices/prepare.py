"""
Opt-in device prep before a crawl — clear obstacles the crawl can't tap past.

Two knobs, both destructive so both opt-in:
  * **grant** runtime permissions up front, so a permission dialog never gates a
    flow (and the generated tests start from a granted state); and
  * **reset** app state (wipe data), so a stale session / half-finished onboarding
    from a previous run doesn't skew the crawl.

Command building is pure and unit tested; only :func:`prepare_device` shells out,
best-effort (a permission the app doesn't declare just fails harmlessly).
"""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List, Optional

# Dangerous (runtime) Android permissions worth granting up front — pm grant only
# applies to declared runtime permissions, so granting one the app doesn't request
# is a harmless no-op.
_ANDROID_GRANTABLE = (
    "android.permission.CAMERA",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.RECORD_AUDIO",
    "android.permission.READ_CONTACTS",
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE",
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.READ_MEDIA_IMAGES",
    "android.permission.READ_CALENDAR",
)

# iOS privacy services simctl can pre-grant.
_IOS_SERVICES = ("location", "photos", "camera", "microphone", "contacts", "calendar")


def android_prepare_commands(
    package: str,
    serial: Optional[str] = None,
    grant: bool = True,
    reset: bool = False,
    permissions: Optional[List[str]] = None,
) -> List[List[str]]:
    """The adb commands to prep an Android app: optional ``pm clear`` (reset) then
    ``pm grant`` for each permission. Reset first so grants survive it."""
    base = ["adb"] + (["-s", serial] if serial else [])
    cmds: List[List[str]] = []
    if reset:
        cmds.append(base + ["shell", "pm", "clear", package])
    if grant:
        for perm in permissions or _ANDROID_GRANTABLE:
            cmds.append(base + ["shell", "pm", "grant", package, perm])
    return cmds


def ios_prepare_commands(
    bundle_id: str,
    udid: Optional[str] = None,
    grant: bool = True,
    reset: bool = False,
    services: Optional[List[str]] = None,
) -> List[List[str]]:
    """The simctl commands to prep an iOS app: optional privacy reset then a
    privacy grant per service."""
    device = udid or "booted"
    cmds: List[List[str]] = []
    if reset:
        cmds.append(["xcrun", "simctl", "privacy", device, "reset", "all", bundle_id])
    if grant:
        for service in services or _IOS_SERVICES:
            cmds.append(["xcrun", "simctl", "privacy", device, "grant", service, bundle_id])
    return cmds


def prepare_commands(config: Dict[str, Any]) -> List[List[str]]:
    """Build the prep commands for a crawl config's ``prepare`` block (pure)."""
    prep = config.get("prepare") or {}
    if not prep:
        return []
    grant = bool(prep.get("grant", True))
    reset = bool(prep.get("reset", False))
    perms = prep.get("permissions")
    if config.get("platform") == "ios":
        return ios_prepare_commands(config["package"], config.get("udid"), grant, reset, perms)
    return android_prepare_commands(config["package"], config.get("serial"), grant, reset, perms)


def prepare_device(config: Dict[str, Any]) -> int:
    """Run the opt-in prep for ``config['prepare']``; returns how many commands ran.
    Best-effort — a grant the app doesn't declare fails harmlessly."""
    ran = 0
    for cmd in prepare_commands(config):
        try:
            subprocess.run(cmd, capture_output=True, timeout=15)
            ran += 1
        except Exception:
            pass
    return ran
