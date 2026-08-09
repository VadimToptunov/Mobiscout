"""
Pre-crawl device preparation — grant the permissions the app declares and,
optionally, reset its state, so the crawler starts clean and isn't stopped by a
system permission dialog it can't see past.

Both are **opt-in** (config flags ``grant_permissions`` / ``reset_state``); the
default does nothing, because a reset wipes app data. Best-effort throughout — a
missing tool or a permission that can't be granted is skipped, never fatal.

    Android — ``pm grant`` each dangerous ``<uses-permission>``; ``pm clear`` to reset.
    iOS     — ``simctl privacy grant`` each service the Info.plist asks for;
              ``simctl privacy reset all`` to reset.
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

_ANDROID_NS = "http://schemas.android.com/apk/res/android"


def _ios_app_plist(config: Dict[str, Any]) -> bytes:
    """The installed iOS app's Info.plist bytes (via ``simctl get_app_container``),
    or b'' when it can't be read."""
    udid, package = config.get("udid"), config.get("package")
    if not udid or not package:
        return b""
    try:
        r = subprocess.run(
            ["xcrun", "simctl", "get_app_container", udid, package, "app"],
            capture_output=True, text=True, timeout=10,
        )
        app_dir = r.stdout.strip()
        if r.returncode != 0 or not app_dir:
            return b""
        plist = Path(app_dir) / "Info.plist"
        return plist.read_bytes() if plist.is_file() else b""
    except (subprocess.SubprocessError, OSError):
        return b""


def _android_manifest(config: Dict[str, Any]) -> str:
    """The source ``AndroidManifest.xml`` under the config's source dir, or ''."""
    source = config.get("source") or config.get("source_dir")
    if not source:
        return ""
    for candidate in Path(source).rglob("AndroidManifest.xml"):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "<manifest" in text and "uses-permission" in text:
            return text
    return ""

# Runtime (dangerous) permissions — the only ones `pm grant` accepts; granting a
# normal/signature permission errors, so we filter the manifest to this set.
_DANGEROUS_ANDROID = {
    "android.permission.READ_CALENDAR",
    "android.permission.WRITE_CALENDAR",
    "android.permission.CAMERA",
    "android.permission.READ_CONTACTS",
    "android.permission.WRITE_CONTACTS",
    "android.permission.GET_ACCOUNTS",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.RECORD_AUDIO",
    "android.permission.READ_PHONE_STATE",
    "android.permission.CALL_PHONE",
    "android.permission.READ_CALL_LOG",
    "android.permission.WRITE_CALL_LOG",
    "android.permission.BODY_SENSORS",
    "android.permission.SEND_SMS",
    "android.permission.RECEIVE_SMS",
    "android.permission.READ_SMS",
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE",
    "android.permission.READ_MEDIA_IMAGES",
    "android.permission.READ_MEDIA_VIDEO",
    "android.permission.READ_MEDIA_AUDIO",
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.ACTIVITY_RECOGNITION",
}

# iOS Info.plist usage key -> the `simctl privacy` service that grants it. Keys
# with no corresponding simctl service (camera, Face ID, Bluetooth, …) are omitted
# — simctl simply can't preset those.
_IOS_PRIVACY = {
    "NSPhotoLibraryUsageDescription": "photos",
    "NSPhotoLibraryAddUsageDescription": "photos-add",
    "NSLocationWhenInUseUsageDescription": "location",
    "NSLocationAlwaysAndWhenInUseUsageDescription": "location-always",
    "NSLocationAlwaysUsageDescription": "location-always",
    "NSContactsUsageDescription": "contacts",
    "NSMicrophoneUsageDescription": "microphone",
    "NSCalendarsUsageDescription": "calendar",
    "NSRemindersUsageDescription": "reminders",
    "NSMotionUsageDescription": "motion",
    "NSAppleMusicUsageDescription": "media-library",
    "NSSiriUsageDescription": "siri",
}


def android_permissions_from_manifest(manifest_xml: str) -> List[str]:
    """Dangerous ``<uses-permission>`` names from a manifest (the ones ``pm grant``
    accepts). Returns [] on unparseable XML."""
    try:
        root = ET.fromstring(manifest_xml)
    except ET.ParseError:
        return []
    out: List[str] = []
    for el in root.iter("uses-permission"):
        name = el.get(f"{{{_ANDROID_NS}}}name") or el.get("name") or ""
        if name in _DANGEROUS_ANDROID:
            out.append(name)
    return sorted(set(out))


def ios_privacy_services_from_plist(plist: bytes) -> List[str]:
    """`simctl privacy` services for the usage keys an Info.plist declares. Returns
    [] on a malformed plist."""
    import plistlib

    try:
        data = plistlib.loads(plist)
    except Exception:
        return []
    services = {svc for key, svc in _IOS_PRIVACY.items() if key in data}
    return sorted(services)


def _run(cmd: List[str]) -> bool:
    """Run a prep command, True on success. Best-effort: never raises."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def prepare_device(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the opt-in pre-crawl preset for ``config``; returns what it did.

    Honours ``grant_permissions`` and ``reset_state`` (both default off). Reset runs
    before grant, since a reset clears previously granted permissions. Never raises.
    Returns ``{platform, granted: [...], reset: bool}``.
    """
    platform = config.get("platform", "android")
    grant = bool(config.get("grant_permissions"))
    reset = bool(config.get("reset_state"))
    result: Dict[str, Any] = {"platform": platform, "granted": [], "reset": False}
    if not grant and not reset:
        return result

    if platform == "ios":
        udid, bundle = config.get("udid"), config.get("package")
        if reset and udid:
            cmd = ["xcrun", "simctl", "privacy", udid, "reset", "all"] + ([bundle] if bundle else [])
            result["reset"] = _run(cmd)
        if grant and udid and bundle:
            for svc in ios_privacy_services_from_plist(_ios_app_plist(config)):
                if _run(["xcrun", "simctl", "privacy", udid, "grant", svc, bundle]):
                    result["granted"].append(svc)
    elif platform == "android":
        serial, pkg = (config.get("udid") or config.get("serial")), config.get("package")
        if reset and serial and pkg:
            result["reset"] = _run(["adb", "-s", serial, "shell", "pm", "clear", pkg])
        if grant and serial and pkg:
            for perm in android_permissions_from_manifest(_android_manifest(config)):
                if _run(["adb", "-s", serial, "shell", "pm", "grant", pkg, perm]):
                    result["granted"].append(perm)
    return result
