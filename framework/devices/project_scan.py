"""
Detect the app(s) in a project directory — the "point at your project" foundation.

A repo can hold more than one app: an Android module and an iOS project side by side,
or several apps in a monorepo. So this returns a **list** of detected apps, each with
what a crawl needs derived automatically — platform, package/bundle id, the source
module, and a build artifact if one is already sitting in the usual output dir. The
user then picks which app(s) to generate for (and, later, run in parallel) instead of
typing any of it by hand.

Best-effort and offline: unreadable/odd projects are skipped, never fatal. Heuristic —
it favours the common Gradle/Xcode layouts and does not shell out to the build tools.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

_ANDROID_NS = "http://schemas.android.com/apk/res/android"
# Dirs that never hold source we care about — skip them so a huge build/ or node_modules
# doesn't dominate the scan.
_SKIP_DIRS = {"build", ".gradle", ".git", "node_modules", "DerivedData", "Pods", ".idea"}


def _under_skipped(path: Path, root: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.relative_to(root).parts[:-1])


def _android_application_id(module_dir: Path) -> Optional[str]:
    """The Gradle ``applicationId`` for a module, if a build.gradle(.kts) declares one."""
    for name in ("build.gradle.kts", "build.gradle"):
        gradle = module_dir / name
        if not gradle.is_file():
            continue
        try:
            text = gradle.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"""applicationId\s*=?\s*["']([\w.]+)["']""", text)
        if m:
            return m.group(1)
    return None


def _android_manifest_package(manifest: Path) -> Optional[str]:
    try:
        root = ET.parse(manifest).getroot()
    except (ET.ParseError, OSError):
        return None
    pkg = root.get("package")
    return pkg or None


def _first_apk(module_dir: Path) -> Optional[str]:
    """A built .apk under the module's output dir, preferring a debug build."""
    outputs = module_dir / "build" / "outputs" / "apk"
    if not outputs.is_dir():
        return None
    apks = sorted(outputs.rglob("*.apk"))
    if not apks:
        return None
    debug = [a for a in apks if "debug" in a.name.lower()]
    return str((debug or apks)[0])


def _detect_android(root: Path) -> List[Dict[str, Any]]:
    apps: List[Dict[str, Any]] = []
    for manifest in root.rglob("AndroidManifest.xml"):
        if _under_skipped(manifest, root):
            continue
        # …/<module>/src/main/AndroidManifest.xml -> module is three parents up.
        parents = manifest.parents
        module_dir = parents[2] if len(parents) >= 3 else manifest.parent
        package = _android_application_id(module_dir) or _android_manifest_package(manifest)
        if not package:
            continue
        apps.append(
            {
                "platform": "android",
                "package": package,
                "source": str(module_dir),
                "build_path": _first_apk(module_dir),
            }
        )
    return apps


def _ios_bundle_id(xcodeproj: Path) -> Optional[str]:
    """The app target's PRODUCT_BUNDLE_IDENTIFIER from the .pbxproj, skipping test targets
    and unresolved ``$(...)`` values."""
    pbxproj = xcodeproj / "project.pbxproj"
    try:
        text = pbxproj.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for m in re.finditer(r"PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([^;]+);", text):
        value = m.group(1).strip().strip('"')
        if "$" in value or not value:
            continue  # a build-variable reference we can't resolve statically
        if value.lower().endswith((".tests", ".uitests", "tests")):
            continue
        return value
    return None


def _detect_ios(root: Path) -> List[Dict[str, Any]]:
    apps: List[Dict[str, Any]] = []
    for xcodeproj in root.rglob("*.xcodeproj"):
        if not xcodeproj.is_dir() or _under_skipped(xcodeproj, root):
            continue
        bundle_id = _ios_bundle_id(xcodeproj)
        if not bundle_id:
            continue
        apps.append(
            {
                "platform": "ios",
                "package": bundle_id,
                "source": str(xcodeproj.parent),
                "build_path": None,
            }
        )
    return apps


def detect_apps(root: str) -> List[Dict[str, Any]]:
    """The apps found under ``root`` — a list of ``{platform, package, source, build_path}``,
    de-duplicated by (platform, package). Empty when nothing is recognised. Never raises."""
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    apps = _detect_android(root_path) + _detect_ios(root_path)
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for app in apps:
        key = (app["platform"], app["package"])
        if key not in seen:
            seen.add(key)
            unique.append(app)
    return unique
