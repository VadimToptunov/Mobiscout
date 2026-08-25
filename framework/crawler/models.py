"""Crawler value types and the driver protocol.

Extracted from app_crawler.py: the duck-typed CrawlerDriver surface and the
CrawlElement / CrawlScreen / CrawlResult dataclasses that flow through the whole
crawl → codegen pipeline. Kept dependency-free so any layer can import them
without pulling in the crawler engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Protocol, Tuple


class CrawlerDriver(Protocol):
    """Minimal driver surface the crawler needs (duck-typed)."""

    def page_source(self) -> str: ...

    def tap(self, x: int, y: int) -> None: ...

    def type_text(self, text: str) -> None: ...  # type into the focused field

    # Optional: clear the focused field before typing. Drivers that implement it keep a
    # re-fill (negative probe then positive fill) from appending onto leftover text;
    # those that don't still work (the field simply keeps its prior contents).
    def clear_field(self) -> None: ...

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
class Transition:
    """One recorded navigation edge.

    ``kind`` distinguishes a real tap from synthetic edges so codegen can treat them
    differently: a ``probe`` edge (a form submitted with invalid data to reach its error
    state) must never become a positive journey, and a ``gate`` edge is the synthetic
    auth crossing. Iterable and indexable as the legacy ``(src, element, dst)`` triple, so
    existing ``for a, b, c in transitions`` / ``t[0]`` consumers keep working unchanged.
    """

    src: str
    element: "CrawlElement"
    dst: str
    kind: str = "tap"  # "tap" | "gate" | "probe"

    def __iter__(self) -> Iterator[Any]:
        return iter((self.src, self.element, self.dst))

    def __getitem__(self, index: int) -> Any:
        return (self.src, self.element, self.dst)[index]


@dataclass
class CrawlResult:
    """Outcome of a crawl: unique screens, transitions, and steps taken."""

    screens: Dict[str, CrawlScreen] = field(default_factory=dict)
    # Recorded navigation edges (see Transition). Kept as objects so codegen can tell a
    # real tap from a gate/probe; still unpacks as (from_fp, element, to_fp).
    transitions: List["Transition"] = field(default_factory=list)
    steps: int = 0
    # Fingerprints of screens reached only after passing a gate (login/OTP/...), so
    # codegen can prepend the auth steps that a generated test needs to get there.
    gated: set = field(default_factory=set)
    # The gate-passing waypoints in the order they actually fired (login -> OTP ->
    # passcode), deduped — codegen emits the auth prefix in this execution order,
    # not the (specificity-ordered) config order.
    auth_sequence: list = field(default_factory=list)
