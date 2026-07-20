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

from framework.crawler.errors import CrawlerDriverError

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


@dataclass
class _Frame:
    """One screen on the depth-first stack: the untried elements to tap, the
    element identities already queued for it (so scrolling doesn't re-enqueue
    them), and how many times we've scrolled it to reveal more."""

    fingerprint: str
    todo: Deque["CrawlElement"]
    seen: set
    scrolls: int = 0


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
        # XCUITest reports off-screen / covered elements (e.g. everything behind a
        # modal auth gate) with visible="false". Including them floods the
        # inventory with phantom elements and makes the crawler waste steps tapping
        # controls that aren't hittable — keep only what's actually on screen.
        if node.get("visible") == "false":
            continue
        itype = (node.get("type") or node.tag).replace("XCUIElementType", "")
        # XCUITest has no scrollable/checkable/focusable attributes, so infer them
        # from the element type — the same signal a human reads off the class.
        enabled = node.get("enabled") != "false"
        # iOS `name` is the accessibility identifier -> map to content_desc so it
        # becomes an ACCESSIBILITY_ID selector (correct cross-platform in Appium).
        elements.append(
            CrawlElement(
                resource_id="",
                text=(node.get("label") or node.get("value") or ""),
                content_desc=node.get("name", ""),
                class_name=itype,
                clickable=itype in _IOS_INTERACTIVE and enabled,
                bounds=(x, y, x + w, y + h),
                scrollable=itype in ("ScrollView", "Table", "CollectionView"),
                focusable=itype in ("TextField", "SecureTextField", "SearchField"),
                checkable=itype in ("Switch",),
                password=itype == "SecureTextField",
                enabled=enabled,
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

    # How many times to scroll one screen looking for more content before moving
    # on — enough to walk a long list, bounded so a screen can't loop forever.
    _MAX_SCROLLS = 8

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

    # Labels safe to tap to clear a blocking system dialog (an ANR "isn't
    # responding", a runtime permission, a system prompt) WITHOUT leaving the app.
    # "Close app" / "Don't allow" / "Deny" would kill or block it, so they're out.
    _SAFE_DIALOG_LABELS = ("wait", "allow", "while using", "only this time", "ok", "continue", "got it")

    def _clear_blocking_dialog(self) -> bool:
        """A capricious device throws blocking dialogs over the app — an ANR, a
        permission request, a system prompt — with no content of the app's own.
        Tap a benign button that keeps the app alive so the crawl can carry on.
        Returns whether it dismissed something."""
        try:
            screen = parse_screen(self.driver.page_source())
        except Exception:
            return False
        for element in screen.elements:
            label = (element.text or element.content_desc or "").strip().lower()
            if label and element.bounds and any(k in label for k in self._SAFE_DIALOG_LABELS):
                self.driver.tap(*element.center)
                return True
        return False

    def _read_content_screen(self, tries: int = 4) -> CrawlScreen:
        """Read the current screen, retrying through a blank / still-loading launch
        — a slow cold start on a busy device yields an empty first dump. Uses the
        driver's refresh() (wait + re-read) when available."""
        screen = parse_screen(self.driver.page_source())
        refresh = getattr(self.driver, "refresh", None)
        attempts = 0
        while (not screen.fingerprint or not screen.elements) and attempts < tries and callable(refresh):
            attempts += 1
            try:
                screen = parse_screen(refresh())
            except Exception:
                break
        return screen

    def _recover(self, tries: int = 3) -> bool:
        """Get back onto the app under test after drift — clear any blocking system
        dialog (ANR/permission) that Back can't, else press Back. If the app has
        drifted away entirely (backgrounded, a foreign app took over), re-launch it
        to the foreground as a last resort. Capricious devices make this the
        difference between a real crawl and an empty one."""
        for _ in range(tries):
            if self._on_app():
                return True
            if not self._clear_blocking_dialog():
                self.driver.back()
        if not self._on_app():
            launch = getattr(self.driver, "launch", None)
            if callable(launch):
                try:
                    launch(self.app_package)
                except Exception:
                    pass
        return self._on_app()

    # Labels on controls that close a modal sheet when Back (an edge-swipe) won't.
    _DISMISS_LABELS = ("close", "cancel", "done", "dismiss", "×", "x", "✕")

    def _current_fp(self) -> str:
        return parse_screen(self.driver.page_source()).fingerprint

    def _go_back(self, parent_fp: str) -> None:
        """Return to ``parent_fp``. Back pops a navigation push, but on iOS it is
        an edge-swipe that does *not* dismiss a modal sheet — so if we're still not
        on the parent we tap a Close/Cancel/Done control, then fall back to a
        swipe-down. Without this the crawl gets stranded on the first sheet it opens
        and every later tap lands on the wrong screen."""
        self.driver.back()
        self._recover()
        if not parent_fp or self._current_fp() == parent_fp:
            return
        # Still off the parent — likely a modal. Try an explicit dismissal control.
        screen = parse_screen(self.driver.page_source())
        for element in screen.interactive():
            label = element.label.strip().lower()
            if self._own(element) and (label in self._DISMISS_LABELS or "close" in label or "cancel" in label):
                self.driver.tap(*element.center)
                self._recover()
                if self._current_fp() == parent_fp:
                    return
                break
        # Last resort: a downward swipe, the near-universal "dismiss sheet" gesture.
        self._scroll("up")
        self._recover()

    @staticmethod
    def _screen_bottom(screen: CrawlScreen) -> int:
        """Lowest pixel any element reaches — a proxy for screen height (the tree
        carries no viewport size), used to spot the bottom navigation strip."""
        return max((e.bounds[3] for e in screen.elements if e.bounds), default=0)

    def _in_bottom_strip(self, element: CrawlElement, bottom: int) -> bool:
        """Whether the element's vertical center sits in the bottom 15% of the
        screen — the band where a tab bar / bottom navigation lives."""
        return bool(element.bounds) and (element.bounds[1] + element.bounds[3]) / 2 >= bottom * 0.85

    def _is_primary_nav(self, element: CrawlElement, screen: CrawlScreen) -> bool:
        """Is this a primary-navigation control — an iOS UITabBar entry or an
        Android BottomNavigationView item?

        These are the highest-leverage things to tap: each opens a whole section
        of the app, and (unlike a pushed screen) the bar is *persistent*, so it is
        reachable from anywhere without relying on Back. Detected by explicit type,
        or by being one of a *row* of controls in the bottom strip — a lone bottom
        button (a form's "Continue", a detail's "Buy") is not navigation.
        """
        if element.class_name in ("Tab", "TabBar", "SegmentedControl"):
            return True
        bottom = self._screen_bottom(screen)
        if bottom <= 0 or element.class_name not in ("Button", "Cell", "Tab"):
            return False
        if not self._in_bottom_strip(element, bottom):
            return False
        row = sum(
            1
            for e in screen.interactive()
            if e.class_name in ("Button", "Cell", "Tab") and self._in_bottom_strip(e, bottom)
        )
        return row >= 3

    def _own_interactive(self, screen: CrawlScreen, exclude_nav: bool = False) -> Deque[CrawlElement]:
        """App-owned tappable elements, primary navigation first.

        ``exclude_nav`` drops the primary-nav bar entirely — used while exploring
        inside one section so the crawl doesn't hop into a *sibling* tab (those are
        driven from the top level, where the persistent bar is a reliable anchor).
        """
        own = [e for e in screen.interactive() if self._own(e)]
        if exclude_nav:
            own = [e for e in own if not self._is_primary_nav(e, screen)]
        # Stable sort: nav bar first, everything else in tree order.
        own.sort(key=lambda e: 0 if self._is_primary_nav(e, screen) else 1)
        return deque(own)

    def crawl(self) -> CrawlResult:
        """Explore the app and return the screen/flow map.

        A transient driver failure (e.g. a wedged adb round-trip that outlived its
        retries, surfaced as :class:`CrawlerDriverError`) ends the crawl early but
        never loses work — every screen and transition gathered before the failure
        is returned, so a single device hiccup degrades to a partial kit instead of
        crashing the whole run.
        """
        result = CrawlResult()
        try:
            self._explore(result)
        except CrawlerDriverError:
            pass  # keep the partial map gathered so far
        return result

    def _explore(self, result: CrawlResult) -> None:
        # Only crawl if we actually start on the app under test — recover first from
        # any launch-time drift or blocking dialog (capricious devices are common).
        if not self._on_app():
            self._recover()
            if not self._on_app():
                return
        # Read through a blank/loading launch, then clear a blocking dialog (ANR /
        # permission) sitting over the app with none of its own content on screen.
        screen = self._read_content_screen()
        for _ in range(3):
            if self._content_count(screen) > 0 or not self._clear_blocking_dialog():
                break
            screen = self._read_content_screen()
        if not screen.fingerprint:
            return
        result.screens[screen.fingerprint] = screen

        # Pass any gate on the entry screen (e.g. a login form) before exploring.
        if self._pass_gates(screen):
            passed = parse_screen(self.driver.page_source())
            if passed.fingerprint:
                screen = passed
                result.screens.setdefault(screen.fingerprint, screen)

        # Tab-based apps (a persistent bottom bar with several entries) are the
        # common case a plain depth-first crawl gets wrong: it burns its step
        # budget deep in the first tab and never reaches the others, and Back
        # (an edge-swipe on iOS) does not switch tabs. So when we see a nav bar,
        # drive each section from its tab — a single tap on the persistent bar is
        # a reliable way to re-anchor between sections.
        nav = [e for e in screen.interactive() if self._own(e) and self._is_primary_nav(e, screen)]
        if len(nav) >= 2:
            self._explore_tabs(result, screen, nav)
        else:
            self._dfs(result, screen.fingerprint, self._own_interactive(screen))

    def _reanchor(self, tab: CrawlElement, target_fp: str, result: CrawlResult, tries: int = 3) -> bool:
        """Return to a tab's root screen by tapping its (persistent) bar entry.

        A previous section's exploration may have left us deep inside a pushed
        screen or modal where the bar is hidden, so we Back out and retry until the
        tap lands us back on the section root (or we give up)."""
        for _ in range(tries):
            self.driver.tap(*tab.center)
            result.steps += 1
            if not self._on_app():
                self._recover()
            if parse_screen(self.driver.page_source()).fingerprint == target_fp:
                return True
            self.driver.back()  # dismiss whatever is covering the bar, then retry
            result.steps += 1
            self._recover()
        return False

    def _explore_tabs(self, result: CrawlResult, home: CrawlScreen, nav: List[CrawlElement]) -> None:
        """Crawl a tab-based app breadth-first, then depth-first.

        Pass 1 taps every tab once to register all section roots — so even on a
        tight step budget the whole top level is mapped, instead of the crawl
        sinking all its steps into the first tab. Pass 2 re-anchors on each tab
        (the bar is persistent) and depth-first explores inside it, excluding the
        nav bar so it never wanders into a sibling tab.
        """
        roots: List[Tuple[CrawlElement, CrawlScreen]] = []
        seen_fps = set()
        for tab in nav:
            if result.steps >= self.max_steps:
                break
            self.driver.tap(*tab.center)
            result.steps += 1
            if not self._on_app():
                self._recover()
                continue
            section = parse_screen(self.driver.page_source())
            if not section.fingerprint:
                continue
            result.transitions.append((home.fingerprint, tab, section.fingerprint))
            if section.fingerprint in seen_fps:
                continue  # two tabs landing on the same screen (e.g. the current one)
            seen_fps.add(section.fingerprint)
            result.screens.setdefault(section.fingerprint, section)
            roots.append((tab, section))

        for tab, section in roots:
            if result.steps >= self.max_steps:
                break
            if not self._reanchor(tab, section.fingerprint, result):
                continue  # can't get back to this section; its root is still mapped
            self._dfs(result, section.fingerprint, self._own_interactive(section, exclude_nav=True), exclude_nav=True)

    @staticmethod
    def _element_key(element: CrawlElement) -> Tuple[str, str, str]:
        """Identity of an element within one screen — stable across scrolling, so
        we don't re-enqueue a control we've already queued after a scroll."""
        return (element.class_name, element.content_desc, element.text)

    def _scroll(self, direction: str = "down") -> bool:
        """Ask the driver to scroll, if it can. Returns whether a scroll happened."""
        scroll = getattr(self.driver, "scroll", None)
        if not callable(scroll):
            return False
        try:
            scroll(direction)
        except Exception:
            return False
        return True

    def _reveal_more(self, seen: set, exclude_nav: bool) -> Deque[CrawlElement]:
        """Scroll down and return app elements newly brought on screen (not already
        seen on this frame). Off-screen content — long lists, below-the-fold links —
        is the single biggest thing a tap-only crawl misses."""
        fresh: Deque[CrawlElement] = deque()
        if not self._scroll("down") or not self._on_app():
            return fresh
        for element in self._own_interactive(parse_screen(self.driver.page_source()), exclude_nav=exclude_nav):
            key = self._element_key(element)
            if key not in seen:
                seen.add(key)
                fresh.append(element)
        return fresh

    # Below this many content (non-nav) controls a freshly-entered screen looks
    # empty — likely still loading — so we give async content a second look.
    _SPARSE_CONTENT = 1

    def _content_count(self, screen: CrawlScreen) -> int:
        """Number of app-owned, non-navigation interactive controls on the screen —
        how much *content* it has, ignoring the ever-present nav bar. A near-zero
        count means the screen looks empty (often still loading)."""
        return sum(1 for e in screen.interactive() if self._own(e) and not self._is_primary_nav(e, screen))

    def _await_content(self, screen: CrawlScreen) -> CrawlScreen:
        """A screen that lands looking empty may just be loading (SwiftUI `.task`,
        a network fetch): wait once more and re-read, keeping whichever view has
        more content. Without this, async screens are captured as blank skeletons
        and their real content is never mapped."""
        refresh = getattr(self.driver, "refresh", None)
        if not callable(refresh) or self._content_count(screen) > self._SPARSE_CONTENT:
            return screen
        try:
            reloaded = parse_screen(refresh())
        except Exception:
            return screen
        if reloaded.fingerprint and self._content_count(reloaded) > self._content_count(screen):
            return reloaded
        return screen

    def _dfs(
        self, result: CrawlResult, root_fp: str, root_todo: Deque[CrawlElement], exclude_nav: bool = False
    ) -> None:
        """Depth-first walk from one root screen, tapping untried elements and
        backing out of dead ends. Shared by the single-root and per-tab crawls."""
        stack: List[_Frame] = [_Frame(root_fp, root_todo, {self._element_key(e) for e in root_todo})]

        while stack and result.steps < self.max_steps:
            frame = stack[-1]
            current_fp, todo = frame.fingerprint, frame.todo
            if not todo:
                # Before giving up on this screen, scroll to see if there is more
                # below the fold; only pop once scrolling reveals nothing new.
                if frame.scrolls < self._MAX_SCROLLS:
                    frame.scrolls += 1
                    result.steps += 1
                    fresh = self._reveal_more(frame.seen, exclude_nav)
                    if fresh:
                        todo.extend(fresh)
                        continue
                stack.pop()
                if stack:  # return to the parent screen (dismissing any modal)
                    result.steps += 1
                    self._go_back(stack[-1].fingerprint)
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

            # Read through a racing/partial UI dump (uiautomator can return an empty
            # or half-built tree right after a transition) rather than dropping the
            # screen on the first empty read.
            new_screen = self._read_content_screen()
            if not new_screen.fingerprint:
                continue

            if new_screen.fingerprint != current_fp:
                # Navigated somewhere new — give async-loaded content a second look
                # before we fingerprint and record it.
                new_screen = self._await_content(new_screen)

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
                child = self._own_interactive(new_screen, exclude_nav=exclude_nav)
                stack.append(_Frame(new_screen.fingerprint, child, {self._element_key(e) for e in child}))
            else:
                # Already seen (or depth cap): don't re-explore, return to parent.
                result.steps += 1
                self._go_back(current_fp)
