"""Crawler value types and the driver protocol.

Extracted from app_crawler.py: the duck-typed CrawlerDriver surface and the
CrawlElement / CrawlScreen / CrawlResult dataclasses that flow through the whole
crawl → codegen pipeline. Kept dependency-free so any layer can import them
without pulling in the crawler engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Tuple


class CrawlerDriver(Protocol):
    """Minimal driver surface the crawler needs (duck-typed)."""

    def page_source(self) -> str: ...

    def tap(self, x: int, y: int) -> None: ...

    def type_text(self, text: str) -> None: ...  # type into the focused field

    def back(self) -> None: ...

    def current_package(self) -> str: ...

    # Optional: reveal off-screen content. Drivers that implement it let the crawl
    # reach below-the-fold links and long-list rows; those that don't still work.
    def scroll(self, direction: str = "down") -> None: ...


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
    # Behavioural attributes — the signals that tell a *generic* container's real
    # role apart (a clickable View is a button, a scrollable one a list, a
    # checkable one a toggle). Captured so the classifier isn't blind to them.
    scrollable: bool = False
    focusable: bool = False
    checkable: bool = False
    password: bool = False
    enabled: bool = True

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
