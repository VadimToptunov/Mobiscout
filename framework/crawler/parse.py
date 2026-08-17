"""Page-source parsing: turn a uiautomator (Android) or XCUITest (iOS) UI dump
into a platform-neutral CrawlScreen.

Extracted from app_crawler.py. Self-contained: it depends only on the crawler
value types in :mod:`framework.crawler.models`.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from framework.crawler.models import CrawlElement, CrawlScreen

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _parse_bounds(raw: str) -> Optional[Tuple[int, int, int, int]]:
    m = _BOUNDS_RE.search(raw or "")
    if not m:
        return None
    x1, y1, x2, y2 = (int(g) for g in m.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


# iOS element types that are tappable (used to infer "clickable" — XCUITest has
# no clickable attribute).
_IOS_INTERACTIVE = {
    "Button",
    "Cell",
    "Link",
    "TextField",
    "SecureTextField",
    "SearchField",
    "Switch",
    "Slider",
    "MenuItem",
    "Tab",
    "TabBar",
    "SegmentedControl",
    "PickerWheel",
    "Stepper",
}


def _parse_android(root: ET.Element) -> List[CrawlElement]:
    elements: List[CrawlElement] = []
    for node in root.iter():
        bounds = _parse_bounds(node.get("bounds", ""))
        if bounds is None:
            continue
        elements.append(
            CrawlElement(
                resource_id=node.get("resource-id", ""),
                text=node.get("text", ""),
                content_desc=node.get("content-desc", ""),
                class_name=node.get("class", node.tag),
                clickable=node.get("clickable") == "true",
                bounds=bounds,
                package=node.get("package", ""),
                scrollable=node.get("scrollable") == "true",
                focusable=node.get("focusable") == "true",
                checkable=node.get("checkable") == "true",
                password=node.get("password") == "true",
                enabled=node.get("enabled") != "false",
            )
        )
    return elements


# iOS applications that own system UI (permission alerts, the springboard / home
# screen) rather than the app under test. XCUITest reports these as a *separate*
# XCUIElementTypeApplication (e.g. name="SpringBoard") alongside the app; their
# elements must never be tapped — the same "don't tap a foreign app / system
# dialog" guard the Android crawler gets for free from each node's `package`.
_IOS_SYSTEM_APPS = {"springboard"}


def _ios_element(node: ET.Element, package: str) -> Optional[CrawlElement]:
    """Build a CrawlElement for one XCUITest node (owned by ``package``), or None
    if it isn't a real, on-screen, positioned element."""
    try:
        x, y = int(float(node.get("x", ""))), int(float(node.get("y", "")))
        w, h = int(float(node.get("width", ""))), int(float(node.get("height", "")))
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    # XCUITest reports off-screen / covered elements (e.g. everything behind a
    # modal auth gate) with visible="false". Including them floods the inventory
    # with phantom elements and makes the crawler waste steps tapping controls that
    # aren't hittable — keep only what's actually on screen.
    if node.get("visible") == "false":
        return None
    itype = (node.get("type") or node.tag).replace("XCUIElementType", "")
    # XCUITest has no scrollable/checkable/focusable attributes, so infer them from
    # the element type — the same signal a human reads off the class.
    enabled = node.get("enabled") != "false"
    # iOS field semantics (matching Android's): `name` is the accessibility
    # IDENTIFIER — a locator like "order.placeButton", NOT a screen-reader label —
    # so it belongs in `resource_id` (the locator field). The screen-reader
    # description is the accessibility LABEL, so `label` -> `content_desc` (the same
    # semantics as Android's contentDescription); `value` remains the element `text`.
    # Conflating identifier with label previously hid every missing-label defect.
    return CrawlElement(
        resource_id=node.get("name", ""),
        text=node.get("value", ""),
        content_desc=node.get("label", ""),
        class_name=itype,
        clickable=itype in _IOS_INTERACTIVE and enabled,
        bounds=(x, y, x + w, y + h),
        package=package,
        scrollable=itype in ("ScrollView", "Table", "CollectionView"),
        focusable=itype in ("TextField", "SecureTextField", "SearchField"),
        checkable=itype in ("Switch",),
        password=itype == "SecureTextField",
        enabled=enabled,
    )


def _parse_ios(root: ET.Element) -> List[CrawlElement]:
    elements: List[CrawlElement] = []
    # The app under test is the first XCUIElementTypeApplication in the tree; its
    # subtree carries package="" (owned). Any *other* application (SpringBoard, a
    # system permission alert) tags its subtree with that app's name, so _own
    # excludes it — giving iOS the foreign-app guard Android has via `package`.
    primary: Dict[str, Optional[str]] = {"name": None}

    def _walk(node: ET.Element, package: str) -> None:
        itype = node.get("type") or node.tag
        if itype.endswith("Application"):
            name = node.get("name", "")
            if primary["name"] is None:
                primary["name"] = name
            is_own = name == primary["name"] and name.lower() not in _IOS_SYSTEM_APPS
            package = "" if is_own else (name or "system")
        element = _ios_element(node, package)
        if element is not None:
            elements.append(element)
        for child in node:
            _walk(child, package)

    _walk(root, "")
    return elements


def _fingerprint(elements: List[CrawlElement]) -> str:
    # Structural signature, ignoring volatile text so the same screen with
    # different data matches.
    sig = "|".join(sorted(f"{e.class_name}:{e.resource_id}:{e.content_desc}:{int(e.clickable)}" for e in elements))
    return hashlib.md5(sig.encode()).hexdigest() if elements else ""


def parse_screen(xml: str) -> CrawlScreen:
    """Parse a page source (Android uiautomator OR iOS XCUITest) into a
    platform-neutral CrawlScreen, auto-detecting the source format."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return CrawlScreen(fingerprint="", elements=[])

    is_ios = root.tag.startswith("XCUIElementType") or root.tag == "AppiumAUT"
    elements = _parse_ios(root) if is_ios else _parse_android(root)

    # Detect the UI toolkit so callers know how to test the app.
    classes = " ".join(e.class_name for e in elements)
    if root.get("mtr-web") == "1":
        toolkit = "webview"  # DOM served from a WebView context (Mode 2); drive via a context switch
    elif "WebView" in classes:
        toolkit = "hybrid"  # native shell hosting web content
    elif "Flutter" in classes:
        toolkit = "flutter"  # canvas-rendered; needs Semantics for good locators
    elif "ComposeView" in classes or "androidx.compose" in classes:
        toolkit = "compose"  # single AndroidComposeView; locate by text/desc, not id
    else:
        toolkit = "native"

    return CrawlScreen(
        fingerprint=_fingerprint(elements),
        elements=elements,
        platform="ios" if is_ios else "android",
        toolkit=toolkit,
    )
