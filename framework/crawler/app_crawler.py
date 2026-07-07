"""
Autonomous app crawler — the missing "explore" half of the pipeline.

Given a driver that can read the current UI tree, tap coordinates, and press
back, the crawler walks an app depth-first: it fingerprints each screen, taps
each interactive element it hasn't tried, records the resulting transitions, and
backtracks — building a screen/flow map that can feed the codegen IR.

It is deliberately decoupled from Appium via the CrawlerDriver protocol so the
whole loop is unit-testable with a fake driver and canned page sources; the
AppiumCrawlerDriver adapter wires it to a real device.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Deque, Dict, List, Optional, Protocol, Tuple

if TYPE_CHECKING:
    from framework.crawler.waypoints import Waypoint

# Element labels containing any of these are never tapped — they are
# destructive or would leave the app / session.
DEFAULT_BLOCKLIST = (
    "logout",
    "log out",
    "sign out",
    "signout",
    "delete",
    "remove account",
    "deactivate",
    "pay",
    "buy",
    "purchase",
    "checkout",
    "confirm order",
)

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


class CrawlerDriver(Protocol):
    """Minimal driver surface the crawler needs (duck-typed)."""

    def page_source(self) -> str: ...

    def tap(self, x: int, y: int) -> None: ...

    def type_text(self, text: str) -> None: ...  # type into the focused field

    def back(self) -> None: ...

    def current_package(self) -> str: ...


@dataclass
class CrawlElement:
    """An interactive element located on a screen."""

    resource_id: str
    text: str
    content_desc: str
    class_name: str
    clickable: bool
    bounds: Tuple[int, int, int, int]  # x1, y1, x2, y2
    package: str = ""  # owning app package (Android); "" for iOS

    @property
    def center(self) -> Tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def label(self) -> str:
        return (self.text or self.content_desc or self.resource_id or self.class_name).strip()


@dataclass
class CrawlScreen:
    """A discovered screen: its structural fingerprint and elements."""

    fingerprint: str
    elements: List[CrawlElement]
    platform: str = "android"  # android | ios
    toolkit: str = "native"  # native | flutter | hybrid (webview)

    @property
    def hybrid(self) -> bool:
        return self.toolkit == "hybrid"

    def interactive(self) -> List[CrawlElement]:
        return [e for e in self.elements if e.clickable]


@dataclass
class CrawlResult:
    """Outcome of a crawl: unique screens, transitions, and steps taken."""

    screens: Dict[str, CrawlScreen] = field(default_factory=dict)
    # (from_fp, tapped element, to_fp) — the element is kept so navigation tests
    # can re-tap it, not just its label.
    transitions: List[Tuple[str, "CrawlElement", str]] = field(default_factory=list)
    steps: int = 0


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
            )
        )
    return elements


def _parse_ios(root: ET.Element) -> List[CrawlElement]:
    elements: List[CrawlElement] = []
    for node in root.iter():
        try:
            x, y = int(float(node.get("x", ""))), int(float(node.get("y", "")))
            w, h = int(float(node.get("width", ""))), int(float(node.get("height", "")))
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        itype = (node.get("type") or node.tag).replace("XCUIElementType", "")
        # iOS `name` is the accessibility identifier -> map to content_desc so it
        # becomes an ACCESSIBILITY_ID selector (correct cross-platform in Appium).
        elements.append(
            CrawlElement(
                resource_id="",
                text=(node.get("label") or node.get("value") or ""),
                content_desc=node.get("name", ""),
                class_name=itype,
                clickable=itype in _IOS_INTERACTIVE and node.get("enabled") != "false",
                bounds=(x, y, x + w, y + h),
            )
        )
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
    if "WebView" in classes:
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


class AppCrawler:
    """Depth-first autonomous crawler over an app's screens."""

    def __init__(
        self,
        driver: CrawlerDriver,
        app_package: str,
        max_steps: int = 100,
        max_depth: int = 20,
        blocklist: Tuple[str, ...] = DEFAULT_BLOCKLIST,
        waypoints: Optional[List["Waypoint"]] = None,
    ):
        self.driver = driver
        self.app_package = app_package
        self.max_steps = max_steps
        self.max_depth = max_depth
        self.blocklist = tuple(b.lower() for b in blocklist)
        # Gate-passing instructions (login, TOTP, biometric, permission dialogs)
        # applied on first sight of a matching screen so the crawl goes deeper.
        self.waypoints = list(waypoints or [])
        self._waypointed: set = set()

    def _pass_gates(self, screen: CrawlScreen) -> bool:
        """Apply a matching waypoint once per screen; True if one fired (the
        caller should re-read the screen since the app moved on)."""
        if not self.waypoints or screen.fingerprint in self._waypointed:
            return False
        from framework.crawler.waypoints import apply_first_match

        self._waypointed.add(screen.fingerprint)
        return apply_first_match(self.waypoints, self.driver, screen)

    def _blocked(self, element: CrawlElement) -> bool:
        label = element.label.lower()
        return any(b in label for b in self.blocklist)

    def _own(self, element: CrawlElement) -> bool:
        """Does this element belong to the app under test? System bars, dialogs
        and (after any drift) the launcher have a different package, so we never
        tap them — that is what caused random apps to launch."""
        return element.package in ("", self.app_package)

    def _on_app(self) -> bool:
        return self.driver.current_package() == self.app_package

    def _recover(self, tries: int = 3) -> bool:
        """Press back until we are on the app again (or give up)."""
        for _ in range(tries):
            if self._on_app():
                return True
            self.driver.back()
        return self._on_app()

    def _own_interactive(self, screen: CrawlScreen) -> Deque[CrawlElement]:
        return deque(e for e in screen.interactive() if self._own(e))

    def crawl(self) -> CrawlResult:
        result = CrawlResult()

        # Only crawl if we actually start on the app under test.
        if not self._on_app():
            return result
        screen = parse_screen(self.driver.page_source())
        if not screen.fingerprint:
            return result
        result.screens[screen.fingerprint] = screen

        # Pass any gate on the entry screen (e.g. a login form) before exploring.
        if self._pass_gates(screen):
            passed = parse_screen(self.driver.page_source())
            if passed.fingerprint:
                screen = passed
                result.screens.setdefault(screen.fingerprint, screen)

        # Each stack frame: (screen fingerprint, queue of untried app elements).
        stack: List[Tuple[str, Deque[CrawlElement]]] = [(screen.fingerprint, self._own_interactive(screen))]

        while stack and result.steps < self.max_steps:
            current_fp, todo = stack[-1]
            if not todo:
                stack.pop()
                if stack:  # return to the parent screen
                    self.driver.back()
                    result.steps += 1
                    self._recover()  # ensure back stayed inside the app
                continue

            element = todo.popleft()
            if self._blocked(element) or not self._own(element):
                continue

            x, y = element.center
            self.driver.tap(x, y)
            result.steps += 1

            # Left the app (opened another app / launcher / chooser) -> come back
            # and abandon this branch. Never crawl a foreign screen.
            if not self._on_app():
                self._recover()
                continue

            new_screen = parse_screen(self.driver.page_source())
            if not new_screen.fingerprint:
                continue

            result.transitions.append((current_fp, element, new_screen.fingerprint))

            if new_screen.fingerprint == current_fp:
                continue  # no navigation; keep trying elements on this screen

            if new_screen.fingerprint not in result.screens and len(stack) < self.max_depth:
                result.screens[new_screen.fingerprint] = new_screen
                # Pass a gate on this new screen too (OTP/biometric behind a step).
                if self._pass_gates(new_screen):
                    behind = parse_screen(self.driver.page_source())
                    if behind.fingerprint and behind.fingerprint not in result.screens:
                        result.transitions.append((new_screen.fingerprint, element, behind.fingerprint))
                        result.screens[behind.fingerprint] = behind
                        new_screen = behind
                stack.append((new_screen.fingerprint, self._own_interactive(new_screen)))
            else:
                # Already seen (or depth cap): don't re-explore, return to parent.
                self.driver.back()
                result.steps += 1
                self._recover()

        return result
