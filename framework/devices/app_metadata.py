"""
App-metadata resolution — read an installed/source app's manifest or Info.plist
for a crawl config. Shared by the deeplink discovery and the pre-crawl permission
preset, which both need "the app's declared X" from the same two sources.

Best-effort: a missing tool / file yields an empty result, never an exception.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

ANDROID_NS = "http://schemas.android.com/apk/res/android"


def ios_app_plist(config: Dict[str, Any]) -> bytes:
    """The iOS app's Info.plist bytes. An explicit ``ios_plist`` path in the config
    wins; otherwise the installed app's plist via ``simctl get_app_container``.
    Returns ``b''`` when it can't be read. ``simctl`` returns the raw (often binary)
    plist — ``plistlib`` reads both formats."""
    explicit = config.get("ios_plist")
    if explicit:
        try:
            return Path(explicit).read_bytes()
        except OSError:
            return b""
    udid, package = config.get("udid"), config.get("package")
    if not udid or not package:
        return b""
    try:
        r = subprocess.run(
            ["xcrun", "simctl", "get_app_container", udid, package, "app"],
            capture_output=True,
            text=True,
            # text=True alone decodes with the locale codepage on Windows, where a
            # non-ASCII path raises UnicodeDecodeError; pin UTF-8 with replacement.
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        app_dir = r.stdout.strip()
        if r.returncode != 0 or not app_dir:
            return b""
        plist = Path(app_dir) / "Info.plist"
        return plist.read_bytes() if plist.is_file() else b""
    except (subprocess.SubprocessError, OSError):
        return b""


def android_manifest(config: Dict[str, Any]) -> str:
    """The app's ``AndroidManifest.xml`` text. An explicit ``android_manifest`` path
    in the config wins; otherwise the one under the config's source dir that declares
    intent-filters / permissions. Returns ``''`` if not found. A binary apk manifest
    needs aapt to decode and is a separate path we don't take here."""
    explicit = config.get("android_manifest")
    if explicit:
        try:
            return Path(explicit).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    source = config.get("source") or config.get("source_dir")
    if not source:
        return ""
    for candidate in Path(source).rglob("AndroidManifest.xml"):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "<manifest" in text and ("intent-filter" in text or "uses-permission" in text):
            return text
    return ""
