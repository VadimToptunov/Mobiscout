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


def _labelled_descendant(node: ET.Element) -> "Optional[ET.Element]":
    """The child that carries a clickable node's visible caption, or None.

    Jetpack Compose emits every tappable control as an **anonymous** ``android.view.View``
    with ``clickable="true"`` and no text or content-desc; the caption sits on a
    non-clickable descendant::

        [clickable] android.view.View  ""
            TextView  "Add plant"

    Read literally, that control has no label — it gets no locator, no generated test can
    target it, and coverage reports 0% on an app the crawl actually walked. Since Compose
    is the default for new Android apps, resolving this is what makes them testable.

    Returns the node itself rather than its text, because the *caption* is what a test can
    actually locate: the anonymous parent has nothing to match on, while the child has real
    text. Its bounds lie inside the parent's, so tapping it hits the same control.

    Takes the first labelled descendant in document order and ignores nested clickables,
    whose captions belong to *them*.
    """
    for child in node:
        if child.get("clickable") == "true":
            continue  # a nested control owns its own caption
        if (child.get("text") or child.get("content-desc") or "").strip():
            return child
        deeper = _labelled_descendant(child)
        if deeper is not None:
            return deeper
    return None


def _parse_android(root: ET.Element) -> List[CrawlElement]:
    by_node: Dict[int, CrawlElement] = {}
    elements: List[CrawlElement] = []
    for node in root.iter():
        bounds = _parse_bounds(node.get("bounds", ""))
        if bounds is None:
            continue
        element = CrawlElement(
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
        by_node[id(node)] = element
        elements.append(element)

    # Compose: hand each anonymous clickable's role to the child that carries its caption,
    # so the control has a locator that actually resolves on the device. Copying the caption
    # onto the parent instead would invent an accessibility id the UI tree does not have —
    # generated tests would then look correct and fail to find anything.
    for node in root.iter():
        wrapper = by_node.get(id(node))
        # NB: not `wrapper.label`, which falls back to the class name — for an anonymous
        # Compose wrapper that is always non-empty, so this guard would never fire.
        if wrapper is None or not wrapper.clickable:
            continue
        if (wrapper.text or wrapper.content_desc or wrapper.resource_id).strip():
            continue
        captioned = _labelled_descendant(node)
        target = by_node.get(id(captioned)) if captioned is not None else None
        if target is not None:
            target.clickable = True  # the caption is the handle; its bounds are inside ours
            wrapper.clickable = False  # ...and this anonymous wrapper is no longer a duplicate
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


def _primary_app(root: ET.Element) -> Optional[str]:
    """Name of the application under test: the first XCUIElementTypeApplication that
    isn't system UI.

    Position alone is not enough. XCUITest can list SpringBoard *before* the app
    (a permission alert, the home screen after the app briefly backgrounds), and
    taking that as the app under test tags the real app's subtree as foreign — so
    ``_own`` rejects every element on the screen and the crawl maps nothing.
    """
    names = [node.get("name", "") for node in root.iter() if (node.get("type") or node.tag).endswith("Application")]
    for name in names:
        if name.lower() not in _IOS_SYSTEM_APPS:
            return name
    return names[0] if names else None


def _parse_ios(root: ET.Element) -> List[CrawlElement]:
    elements: List[CrawlElement] = []
    # The app under test's subtree carries package="" (owned). Any *other*
    # application (SpringBoard, a system permission alert) tags its subtree with that
    # app's name, so _own excludes it — giving iOS the foreign-app guard Android has
    # via `package`.
    primary = _primary_app(root)

    def _walk(node: ET.Element, package: str) -> None:
        itype = node.get("type") or node.tag
        if itype.endswith("Application"):
            name = node.get("name", "")
            is_own = name == primary and name.lower() not in _IOS_SYSTEM_APPS
            package = "" if is_own else (name or "system")
        element = _ios_element(node, package)
        if element is not None:
            elements.append(element)
        for child in node:
            _walk(child, package)

    _walk(root, "")
    return elements


def _fp_token(e: CrawlElement) -> str:
    # content-desc often carries volatile per-row data ("Post by Alice, 3 likes")
    # that makes identical feed rows look like distinct screens and defeats dedup —
    # an endless feed then reads as endless screens. So use content-desc only when
    # there's no resource-id to key on (Compose / iOS), and blank digits either way
    # so counts/prices ("3 likes", "$4.99") don't fork one screen into many.
    desc = re.sub(r"\d+", "", e.content_desc) if not e.resource_id else ""
    return f"{e.class_name}:{e.resource_id}:{desc}:{int(e.clickable)}"


def _fingerprint(elements: List[CrawlElement]) -> str:
    # Structural signature, ignoring volatile text so the same screen with
    # different data matches.
    sig = "|".join(sorted(_fp_token(e) for e in elements))
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
