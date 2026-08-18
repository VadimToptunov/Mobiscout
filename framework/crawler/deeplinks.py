"""
Deeplink seeding — reach screens a UI walk can't.

A depth-first crawl from the launcher only sees what's reachable by tapping. Many
screens are reachable *only* by a deeplink — a push-notification target, a
share/return URL, a checkout entered from the web. Seeding opens each deeplink as
an extra crawl root and merges what it finds into the same graph.

This module is the device-free part: pull candidate deeplinks out of an Android
manifest or an iOS Info.plist, or take them verbatim from config. Opening a URI
and crawling from it is the pipeline's job (``driver.open_url`` + merge).
"""

from __future__ import annotations

import plistlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

_ANDROID_NS = "http://schemas.android.com/apk/res/android"


def _attr(el: ET.Element, name: str) -> str:
    return el.get(f"{{{_ANDROID_NS}}}{name}", "")


def _dedupe(items: List[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def deeplinks_from_android_manifest(manifest_xml: str) -> List[str]:
    """Sample deeplink URIs from a decoded AndroidManifest.xml — one per
    ``<intent-filter>`` that is a browsable VIEW filter (a real deeplink, not an
    internal intent). Splits scheme/host/path that Android allows across sibling
    ``<data>`` tags and rebuilds a usable ``scheme://host/path``."""
    try:
        root = ET.fromstring(manifest_xml)
    except ET.ParseError:
        return []
    uris: List[str] = []
    for intent in root.iter("intent-filter"):
        actions = {_attr(a, "name") for a in intent.findall("action")}
        if "android.intent.action.VIEW" not in actions:
            continue
        cats = {_attr(c, "name") for c in intent.findall("category")}
        if "android.intent.category.BROWSABLE" not in cats:
            continue  # a non-browsable VIEW filter isn't an externally-openable deeplink
        schemes, hosts, paths = [], [], []
        for data in intent.findall("data"):
            if _attr(data, "scheme"):
                schemes.append(_attr(data, "scheme"))
            if _attr(data, "host"):
                hosts.append(_attr(data, "host"))
            path = _attr(data, "pathPrefix") or _attr(data, "path") or _attr(data, "pathPattern")
            if path:
                paths.append(path)
        host = hosts[0] if hosts else ""
        path = paths[0].replace(".*", "").replace("(", "").replace(")", "") if paths else ""
        for scheme in schemes:
            if scheme in ("http", "https"):
                if host:
                    uris.append(f"{scheme}://{host}{path}")
            elif host:
                uris.append(f"{scheme}://{host}{path}")
            else:
                uris.append(f"{scheme}://{path.lstrip('/') or 'home'}")
    return _dedupe(uris)


def deeplinks_from_ios_plist(plist: Any) -> List[str]:
    """Custom-scheme deeplinks from an iOS Info.plist — ``scheme://`` for every
    scheme under CFBundleURLTypes. Accepts a parsed dict or raw plist bytes/str."""
    data = plist
    if isinstance(plist, (str, bytes)):
        try:
            data = plistlib.loads(plist.encode() if isinstance(plist, str) else plist)
        except Exception:
            return []
    if not isinstance(data, dict):
        return []
    schemes: List[str] = []
    for entry in data.get("CFBundleURLTypes") or []:
        for scheme in entry.get("CFBundleURLSchemes") or []:
            if scheme:
                schemes.append(f"{scheme}://")
    return _dedupe(schemes)


def extract_deeplinks(config: Dict[str, Any]) -> List[str]:
    """The deeplink seeds for a crawl: an explicit ``deeplinks`` list from config,
    plus any parsed from an ``android_manifest`` / ``ios_plist`` path. The explicit
    list is always included and comes first."""
    seeds: List[str] = list(config.get("deeplinks") or [])
    manifest = config.get("android_manifest")
    if manifest:
        try:
            seeds += deeplinks_from_android_manifest(Path(manifest).read_text(encoding="utf-8"))
        except Exception:
            pass
    plist = config.get("ios_plist")
    if plist:
        try:
            seeds += deeplinks_from_ios_plist(Path(plist).read_bytes())
        except Exception:
            pass
    return _dedupe(seeds)
