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
from typing import Deque, Dict, List, Optional, Protocol, Tuple

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

    def interactive(self) -> List[CrawlElement]:
        return [e for e in self.elements if e.clickable]


@dataclass
class CrawlResult:
    """Outcome of a crawl: unique screens, transitions, and steps taken."""

    screens: Dict[str, CrawlScreen] = field(default_factory=dict)
    transitions: List[Tuple[str, str, str]] = field(default_factory=list)  # (from_fp, label, to_fp)
    steps: int = 0


def _parse_bounds(raw: str) -> Optional[Tuple[int, int, int, int]]:
    m = _BOUNDS_RE.search(raw or "")
    if not m:
        return None
    x1, y1, x2, y2 = (int(g) for g in m.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def parse_screen(xml: str) -> CrawlScreen:
    """Parse an Android uiautomator page source into a CrawlScreen."""
    elements: List[CrawlElement] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return CrawlScreen(fingerprint="", elements=[])

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
            )
        )

    # Structural fingerprint: (class, resource-id, clickable) of each element,
    # ignoring volatile text so the same screen with different data matches.
    signature = "|".join(sorted(f"{e.class_name}:{e.resource_id}:{int(e.clickable)}" for e in elements))
    fingerprint = hashlib.md5(signature.encode()).hexdigest() if elements else ""
    return CrawlScreen(fingerprint=fingerprint, elements=elements)


class AppCrawler:
    """Depth-first autonomous crawler over an app's screens."""

    def __init__(
        self,
        driver: CrawlerDriver,
        app_package: str,
        max_steps: int = 100,
        max_depth: int = 20,
        blocklist: Tuple[str, ...] = DEFAULT_BLOCKLIST,
    ):
        self.driver = driver
        self.app_package = app_package
        self.max_steps = max_steps
        self.max_depth = max_depth
        self.blocklist = tuple(b.lower() for b in blocklist)

    def _blocked(self, element: CrawlElement) -> bool:
        label = element.label.lower()
        return any(b in label for b in self.blocklist)

    def crawl(self) -> CrawlResult:
        result = CrawlResult()

        screen = parse_screen(self.driver.page_source())
        if not screen.fingerprint:
            return result
        result.screens[screen.fingerprint] = screen

        # Each stack frame: (screen fingerprint, queue of untried interactive elements).
        stack: List[Tuple[str, Deque[CrawlElement]]] = [(screen.fingerprint, deque(screen.interactive()))]

        while stack and result.steps < self.max_steps:
            current_fp, todo = stack[-1]
            if not todo:
                stack.pop()
                if stack:  # return to the parent screen
                    self.driver.back()
                    result.steps += 1
                continue

            element = todo.popleft()
            if self._blocked(element):
                continue

            x, y = element.center
            self.driver.tap(x, y)
            result.steps += 1

            # Left the app (external app / launcher / system dialog) -> go back.
            if self.driver.current_package() != self.app_package:
                self.driver.back()
                continue

            new_screen = parse_screen(self.driver.page_source())
            if not new_screen.fingerprint:
                continue

            result.transitions.append((current_fp, element.label, new_screen.fingerprint))

            if new_screen.fingerprint == current_fp:
                continue  # no navigation; keep trying elements on this screen

            if new_screen.fingerprint not in result.screens and len(stack) < self.max_depth:
                result.screens[new_screen.fingerprint] = new_screen
                stack.append((new_screen.fingerprint, deque(new_screen.interactive())))
            else:
                # Already seen (or depth cap): don't re-explore, return to parent.
                self.driver.back()
                result.steps += 1

        return result
