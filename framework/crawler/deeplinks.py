"""
Deeplink discovery — the URIs an app declares it can be opened with.

A crawler that only taps reaches only what's reachable by tapping; deeplinks are
the app's own shortcuts into deep screens (a trip, a payment, a settings page)
that a tap-walk may never reach. This module *extracts* the declared deeplinks so
they can be listed in the kit and (next) opened as extra crawl seeds.

    Android — AndroidManifest.xml ``<intent-filter>`` with action VIEW + category
              BROWSABLE, over its ``<data>`` scheme/host/path.
    iOS     — Info.plist ``CFBundleURLTypes`` custom schemes.

Pure parsers (bytes/str in, list out) so they're testable without a device; the
``extract_deeplinks`` resolver best-effort finds the manifest/plist for a config.
"""

from __future__ import annotations

import plistlib
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from framework.devices.app_metadata import ANDROID_NS as _ANDROID_NS
from framework.devices.app_metadata import android_manifest as _android_manifest
from framework.devices.app_metadata import ios_app_plist as _ios_app_plist


def deeplinks_from_ios_plist(plist: bytes) -> List[str]:
    """Custom URL schemes from an Info.plist's ``CFBundleURLTypes`` as ``scheme://``
    sample URIs. Ignores the http/https universal-link schemes (not app-openable on
    their own). Returns [] on a malformed plist."""
    try:
        data = plistlib.loads(plist)
    except Exception:
        return []
    out: List[str] = []
    for entry in data.get("CFBundleURLTypes", []) or []:
        for scheme in entry.get("CFBundleURLSchemes", []) or []:
            s = str(scheme).strip()
            if s and s not in ("http", "https"):
                out.append(f"{s}://")
    return sorted(set(out))


def deeplinks_from_android_manifest(manifest_xml: str) -> List[str]:
    """Deeplink URIs from an AndroidManifest's browsable VIEW intent-filters.

    For each ``<intent-filter>`` that has both ``action VIEW`` and ``category
    BROWSABLE``, expand its ``<data>`` entries into ``scheme://host/path`` URIs
    (a scheme alone yields ``scheme://``). Returns [] on unparseable XML.
    """
    try:
        root = ET.fromstring(manifest_xml)
    except ET.ParseError:
        return []

    def attr(el: ET.Element, name: str) -> str:
        return el.get(f"{{{_ANDROID_NS}}}{name}") or el.get(name) or ""

    uris: List[str] = []
    for intent in root.iter("intent-filter"):
        actions = {attr(a, "name") for a in intent.findall("action")}
        categories = {attr(c, "name") for c in intent.findall("category")}
        if "android.intent.action.VIEW" not in actions:
            continue
        if "android.intent.category.BROWSABLE" not in categories:
            continue
        schemes = [attr(d, "scheme") for d in intent.findall("data") if attr(d, "scheme")]
        hosts = [attr(d, "host") for d in intent.findall("data") if attr(d, "host")]
        paths = [
            attr(d, "path") or attr(d, "pathPrefix") or attr(d, "pathPattern")
            for d in intent.findall("data")
            if (attr(d, "path") or attr(d, "pathPrefix") or attr(d, "pathPattern"))
        ]
        for scheme in schemes or []:
            if scheme in ("http", "https"):
                continue  # app links; not a custom app-openable scheme on their own
            host = hosts[0] if hosts else ""
            path = paths[0].lstrip("/") if paths else ""
            uri = f"{scheme}://{host}" + (f"/{path}" if path else "")
            uris.append(uri)
    return sorted(set(uris))


def extract_deeplinks(config: Dict[str, Any]) -> List[str]:
    """Declared deeplinks for the app in ``config`` — best-effort, never raises.

    iOS reads the installed app's Info.plist; Android reads the source manifest.
    Returns a sorted, de-duplicated list of URI templates (possibly empty).
    """
    platform = config.get("platform", "android")
    try:
        if platform == "ios":
            return deeplinks_from_ios_plist(_ios_app_plist(config))
        if platform == "android":
            return deeplinks_from_android_manifest(_android_manifest(config))
    except Exception:
        return []
    return []


def deeplinks_markdown(uris: List[str], package: str) -> str:
    """The ``deeplinks.md`` kit artifact."""
    if not uris:
        return f"# Deeplinks — {package}\n\nNo browsable deeplinks were declared by the app.\n"
    lines = [f"# Deeplinks — {package}", "", f"{len(uris)} declared deeplink(s):", ""]
    lines += [f"- `{u}`" for u in uris]
    lines += [
        "",
        "Open one with:",
        "",
        "```bash",
        "# Android",
        "adb shell am start -W -a android.intent.action.VIEW -d '<uri>' " + package,
        "# iOS simulator",
        "xcrun simctl openurl booted '<uri>'",
        "```",
        "",
    ]
    return "\n".join(lines)
