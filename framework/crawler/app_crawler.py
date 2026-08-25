"""
Autonomous app crawler — the missing "explore" half of the pipeline.

Given a driver that can read the current UI tree, tap coordinates, and press
back, the crawler walks an app depth-first: it fingerprints each screen, taps
each interactive element it hasn't tried, records the resulting transitions, and
backtracks — building a screen/flow map that can feed the codegen IR.

It is deliberately decoupled from Appium via the CrawlerDriver protocol so the
whole loop is unit-testable with a fake driver and canned page sources; the
AppiumCrawlerDriver adapter wires it to a real device.

The crawler value types (CrawlerDriver, CrawlElement, CrawlScreen, CrawlResult)
now live in :mod:`framework.crawler.models` and the page-source parsing in
:mod:`framework.crawler.parse`; both are re-exported here so existing imports
(``from framework.crawler.app_crawler import ...``) keep working unchanged.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Deque, Dict, List, Optional, Tuple

from framework.crawler.errors import CrawlerDriverError
from framework.crawler.form_values import (
    _CONTEXT_FINANCIAL_LABELS,
    _FINANCIAL_LABELS,
    _SUBMIT_LABELS,
    _invalid_value,
    _is_money_screen,
    _label_has_token,
    _sample_value,
)
from framework.crawler.models import CrawlElement, CrawlResult, CrawlerDriver, CrawlScreen, Transition
from framework.crawler.obstacles import clear_obstacle, error_retry, terminal_obstacle
from framework.crawler.parse import parse_screen
from framework.utils.logger import get_logger

logger = get_logger(__name__)


if TYPE_CHECKING:
    from framework.crawler.waypoints import Waypoint

__all__ = [
    "CrawlerDriver",
    "CrawlElement",
    "CrawlScreen",
    "CrawlResult",
    "parse_screen",
    "DEFAULT_BLOCKLIST",
    "AppCrawler",
]

# Labels that end the session / leave the app. Tapping these never deepens a
# crawl — it just strands it on a login screen or another app — so they stay
# blocked even in sandbox mode.
SESSION_BLOCKLIST = (
    "logout",
    "log out",
    "sign out",
    "signout",
)

# Labels for destructive or financial actions. Blocked by default so a crawl of a
# real app never deletes data or completes a payment/transfer — but a deliberately
# throwaway app (a sandbox/test build) can opt to let the crawler through these
# to reach the screens behind them (see AppCrawler(..., allow_destructive=True)).
# The financial verbs (pay/buy/transfer/send/confirm/…) are single-sourced in
# form_values._FINANCIAL_LABELS so the submit picker and this blocklist can't drift:
# a control that's a "submit" must also be gated here if it moves money.
DESTRUCTIVE_BLOCKLIST = (
    "delete",
    "remove account",
    "deactivate",
) + _FINANCIAL_LABELS

# Element labels containing any of these are never tapped by default — they are
# destructive or would leave the app / session.
DEFAULT_BLOCKLIST = SESSION_BLOCKLIST + DESTRUCTIVE_BLOCKLIST

# Tap-order priority by semantic role (lower = tapped sooner). High-leverage
# controls first so a bounded crawl spends its budget on navigation and primary
# actions, not decoration. Inputs sit low — focusing them rarely navigates and
# _fill_inputs already types into them; images/plain text sit lowest (often no-op).
_ROLE_PRIORITY = {
    "button": 1,
    "link": 1,
    "switch": 2,
    "checkbox": 2,
    "radio": 2,
    "list": 3,
    "generic": 3,
    "input": 4,
    "image": 5,
    "text": 5,
}
_ROLE_PRIORITY_DEFAULT = 3

# Beyond this many structurally-identical siblings (a list of rows), tapping more
# just re-opens the same detail template with different data — so cap the queue.
_SIBLING_CAP = 3


@dataclass
class _Frame:
    """One screen on the depth-first stack: the untried elements to tap, the
    element identities already queued for it (so scrolling doesn't re-enqueue
    them), and how many times we've scrolled it to reveal more."""

    fingerprint: str
    todo: Deque["CrawlElement"]
    seen: set
    scrolls: int = 0
    # Whether this screen shows a money field — gates the ambiguous financial verbs when
    # the depth-first loop taps this frame's controls (see _blocked).
    money: bool = False


class AppCrawler:
    """Depth-first autonomous crawler over an app's screens."""

    # How many times to scroll one screen looking for more content before moving
    # on. The loop already stops early the moment a scroll reveals nothing new, so
    # this only caps genuinely long lists — where each extra scroll costs a full
    # settle (the crawl's dominant cost), so we keep the cap tight.
    _MAX_SCROLLS = 4

    def __init__(
        self,
        driver: CrawlerDriver,
        app_package: str,
        max_steps: int = 100,
        max_depth: int = 20,
        blocklist: Optional[Tuple[str, ...]] = None,
        waypoints: Optional[List["Waypoint"]] = None,
        allow_destructive: bool = False,
        max_seconds: float = 0.0,
        max_novelty_gap: int = 25,
    ) -> None:
        self.driver = driver
        self.app_package = app_package
        self.max_steps = max_steps
        self.max_depth = max_depth
        # Wall-clock budget (0 = disabled). A step-only budget can't bound a crawl
        # whose per-step device reads are slow (e.g. an Android hybrid screen whose
        # uiautomator dump crawls) — the deadline caps total run time regardless.
        self.max_seconds = max_seconds
        self._deadline = float("inf")
        # Plateau / novelty stop (0 = disabled). The crawl ends once it goes this
        # many steps without discovering a new screen template — coverage has
        # saturated, so it stops instead of re-treading known ground to the hard
        # step cap (an endless feed or deep search would otherwise wander to it). A
        # newly-seen screen re-anchors the counter.
        self.max_novelty_gap = max_novelty_gap
        self._screens_high = 0
        self._step_at_last_new = 0
        # By default block both session-enders and destructive/financial actions.
        # ``allow_destructive`` (for throwaway sandbox/test apps) keeps only the
        # session-enders blocked, so the crawl can tap Pay/Buy/Delete/Confirm and
        # reach the screens behind them. An explicit ``blocklist`` overrides both.
        # Context-gate the ambiguous financial verbs (send/confirm/exchange) only in the
        # default profile — an explicit blocklist is taken literally, and --allow-destructive
        # drops the financial tier entirely.
        self._context_gated = blocklist is None and not allow_destructive
        if blocklist is None:
            blocklist = SESSION_BLOCKLIST if allow_destructive else DEFAULT_BLOCKLIST
        self.blocklist = tuple(b.lower() for b in blocklist)
        # Gate-passing instructions (login, TOTP, biometric, permission dialogs)
        # applied on sight of a matching screen so the crawl goes deeper. Re-firing
        # is bounded per screen (not one-shot) so a gate re-appearing mid-crawl —
        # a session expiring and dropping us back on the login — is passed again,
        # while a gate the fill can't clear can't loop forever.
        self.waypoints = list(waypoints or [])
        self._waypointed: Dict[str, int] = {}
        # Form fingerprints already probed with invalid input — probe each once.
        self._neg_probed: set = set()
        # Flips once any gate is passed; screens recorded afterward are "behind auth"
        # and tagged in result.gated so codegen can prepend the auth steps.
        self._passed_gate = False
        # The waypoints that fired, in execution order (login -> OTP -> passcode),
        # deduped — codegen emits the auth prefix in this order.
        self._fired_waypoints: List["Waypoint"] = []

    def _note_screen(self, result: CrawlResult, fingerprint: str) -> None:
        """Tag a just-recorded screen as behind-auth if a gate has been passed."""
        if self._passed_gate:
            result.gated.add(fingerprint)

    # A gate screen may be re-fired this many times total — enough to re-auth after
    # a session drops us back on login a few times, not enough for a fill that never
    # clears the gate to loop.
    _MAX_WAYPOINT_FIRES = 3
    # One gate-passing pass chains through at most this many *sequential* gates (a
    # login that reveals an OTP that reveals a passcode) before handing back to
    # normal exploration.
    _MAX_GATE_CHAIN = 6

    def _pass_gates(self, screen: CrawlScreen) -> bool:
        """Apply matching waypoints, chaining through a *sequence* of gates — a login
        that reveals an OTP that reveals a passcode — until none matches or the screen
        stops moving. True if any fired (the caller should re-read the screen).

        Chaining matters: without it, passing the login hands the revealed OTP screen
        straight to normal exploration, which types a sample value into it — and an
        auto-submitting OTP field then submits a wrong code. Passing each gate in turn
        with its own waypoint keeps that from happening. Per-screen re-fire stays
        bounded so a gate a fill can't clear never loops."""
        if not self.waypoints:
            return False
        from framework.crawler.waypoints import apply, matches

        current = screen
        fired_any = False
        for _ in range(self._MAX_GATE_CHAIN):
            if self._waypointed.get(current.fingerprint, 0) >= self._MAX_WAYPOINT_FIRES:
                break
            # First matching waypoint (specificity order), applied — but recorded in
            # *fire* order for codegen, so the generated auth prefix runs login ->
            # OTP -> passcode, not the config's specificity order.
            fired = next((wp for wp in self.waypoints if matches(wp, current)), None)
            if fired is None or not apply(fired, self.driver, current):
                break
            if fired not in self._fired_waypoints:
                self._fired_waypoints.append(fired)
            self._waypointed[current.fingerprint] = self._waypointed.get(current.fingerprint, 0) + 1
            fired_any = True
            self._passed_gate = True  # everything recorded from here on is behind auth
            nxt = self._read_content_screen()
            if not nxt.fingerprint or nxt.fingerprint == current.fingerprint:
                break  # this gate didn't move us on — stop (a retry is covered by re-fire)
            current = nxt
        return fired_any

    def _blocked(self, element: CrawlElement, money_context: bool = False) -> bool:
        """Whether this control must not be tapped. Matches blocklist tokens on WORD
        BOUNDARIES (so "send" never fires on "resend"/"sender", "pay" not on "PayPal") and,
        in the default profile, treats the ambiguous financial verbs (send/confirm/exchange)
        as blocked only when ``money_context`` — the screen shows a money field. So an OTP
        "Send code" or a chat "Send" is still crawled, while "Send" on a transfer form is not.
        """
        label = element.label.strip().lower()
        for b in self.blocklist:
            if not _label_has_token(b, label):
                continue
            if self._context_gated and not money_context and b in _CONTEXT_FINANCIAL_LABELS:
                continue  # ambiguous verb, no money field on this screen → not blocked
            return True
        return False

    def _money_screen(self, screen: CrawlScreen) -> bool:
        """Does this screen involve money (a currency symbol / amount field)? Gates the
        ambiguous financial verbs for :meth:`_blocked`."""
        return _is_money_screen(e for e in screen.elements if self._own(e))

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

    # How many stacked non-terminal obstacles (onboarding page, then a consent
    # banner, then a rate-us nag) to clear before treating a screen as content.
    _MAX_OBSTACLES = 5

    def _read_content_screen(self, tries: int = 4) -> CrawlScreen:
        """Read the current screen, retrying through a blank / still-loading launch
        — a slow cold start on a busy device yields an empty first dump. Uses the
        driver's refresh() (wait + re-read) when available. Then auto-clears any
        built-in obstacles (onboarding / consent / nag) sitting over the content."""
        screen = parse_screen(self.driver.page_source())
        refresh = getattr(self.driver, "refresh", None)
        attempts = 0
        while (not screen.fingerprint or not screen.elements) and attempts < tries and callable(refresh):
            attempts += 1
            try:
                screen = parse_screen(refresh())
            except Exception:
                break
        # Dismiss stacked no-input obstacles and retry transient errors (a flaky
        # backend), re-reading after each, so the screen the crawler fingerprints
        # and explores is the real content behind them — not an onboarding page or
        # a "no connection / try again" error. The bounded loop means a persistent
        # error is mapped once instead of retried forever.
        for _ in range(self._MAX_OBSTACLES):
            try:
                if clear_obstacle(self.driver, screen) is None and error_retry(self.driver, screen) is None:
                    break
                screen = parse_screen(self.driver.page_source())
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
        """App-owned tappable elements, ordered by how much they're worth tapping.

        ``exclude_nav`` drops the primary-nav bar entirely — used while exploring
        inside one section so the crawl doesn't hop into a *sibling* tab (those are
        driven from the top level, where the persistent bar is a reliable anchor).
        """
        own = [e for e in screen.interactive() if self._own(e)]
        if exclude_nav:
            own = [e for e in own if not self._is_primary_nav(e, screen)]
        return self._prioritize(own, screen)

    @staticmethod
    def _size_bucket(bounds: Tuple[int, int, int, int]) -> Tuple[int, int, int]:
        """A coarse (column, width, height) signature, so a column of identically
        shaped list rows shares one bucket regardless of vertical position."""
        x1, _y1, x2, y2 = bounds
        return (x1 // 25, (x2 - x1) // 25, (y2 - _y1) // 25)

    def _prioritize(self, elements: List[CrawlElement], screen: CrawlScreen) -> Deque[CrawlElement]:
        """Order tappable elements by semantic value and drop redundant list
        siblings — so a bounded crawl explores the app's *structure* (navigation,
        primary actions) instead of poking every decorative icon and every one of
        twenty identical rows. Primary nav is never dropped; structurally-identical
        siblings beyond :data:`_SIBLING_CAP` are (they re-open the same detail
        template with different data)."""
        # Lazy import: classify imports CrawlElement from this module.
        from framework.crawler.classify import classify

        roles = ["nav" if self._is_primary_nav(e, screen) else classify(e)[0] for e in elements]
        # Stable sort keeps tree order within a rank; nav (0) leads, decoration trails.
        order = sorted(
            range(len(elements)),
            key=lambda i: 0 if roles[i] == "nav" else _ROLE_PRIORITY.get(roles[i], _ROLE_PRIORITY_DEFAULT),
        )
        kept: List[CrawlElement] = []
        counts: dict = {}
        for i in order:
            element, role = elements[i], roles[i]
            if role == "nav":
                kept.append(element)  # every section entry matters — never capped
                continue
            sig = (role, self._size_bucket(element.bounds))
            counts[sig] = counts.get(sig, 0) + 1
            if counts[sig] <= _SIBLING_CAP:
                kept.append(element)
        return deque(kept)

    def crawl(self) -> CrawlResult:
        """Explore the app and return the screen/flow map.

        A transient driver failure (e.g. a wedged adb round-trip that outlived its
        retries, surfaced as :class:`CrawlerDriverError`) ends the crawl early but
        never loses work — every screen and transition gathered before the failure
        is returned, so a single device hiccup degrades to a partial kit instead of
        crashing the whole run.
        """
        result = CrawlResult()
        if self.max_seconds > 0:
            self._deadline = time.monotonic() + self.max_seconds
        try:
            self._explore(result)
        except CrawlerDriverError:
            pass  # expected transient (wedged round-trip) — keep the partial map
        except Exception as exc:  # noqa: BLE001 — device flakiness must never lose work
            # An unexpected driver hiccup (a dropped WDA/Appium session, a socket
            # reset, a malformed dump) must not crash the run and throw away every
            # screen gathered so far — capricious devices are the norm, not a bug.
            logger.warning(
                "crawl ended early on an unexpected driver error (%s); returning partial map", type(exc).__name__
            )
        result.auth_sequence = list(self._fired_waypoints)  # gates in the order passed, for codegen
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
        entry_fp = screen.fingerprint
        entry_link = next((e for e in screen.interactive() if self._own(e)), None)
        if entry_link is None and screen.elements:
            entry_link = screen.elements[0]
        if self._pass_gates(screen):
            passed = parse_screen(self.driver.page_source())
            if passed.fingerprint:
                screen = passed
                result.screens.setdefault(screen.fingerprint, screen)
                self._note_screen(result, screen.fingerprint)
                # Connect the entry to the post-auth screen so it — and everything
                # reachable from it — is nav-reachable in the graph and gets test
                # cases. The synthetic hop is trimmed by the gated nav re-rooting;
                # the prepended auth steps reproduce the crossing.
                if entry_link is not None and passed.fingerprint != entry_fp:
                    result.transitions.append(Transition(entry_fp, entry_link, passed.fingerprint, kind="gate"))

        # Exercise this screen's form both ways (invalid→error, then valid) so
        # form-gated flows are reachable and validation states get discovered.
        self._handle_form(result, screen)

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
            self._dfs(result, screen.fingerprint, self._own_interactive(screen), root_money=self._money_screen(screen))

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
            if not self._within_budget(result):
                break
            self.driver.tap(*tab.center)
            result.steps += 1
            if not self._on_app():
                self._recover()
                continue
            section = parse_screen(self.driver.page_source())
            if not section.fingerprint:
                continue
            result.transitions.append(Transition(home.fingerprint, tab, section.fingerprint))
            if section.fingerprint in seen_fps:
                continue  # two tabs landing on the same screen (e.g. the current one)
            seen_fps.add(section.fingerprint)
            result.screens.setdefault(section.fingerprint, section)
            self._note_screen(result, section.fingerprint)
            self._handle_form(result, section)  # exercise a section root's form both ways
            roots.append((tab, section))

        for tab, section in roots:
            if not self._within_budget(result):
                break
            if not self._reanchor(tab, section.fingerprint, result):
                continue  # can't get back to this section; its root is still mapped
            self._dfs(
                result,
                section.fingerprint,
                self._own_interactive(section, exclude_nav=True),
                exclude_nav=True,
                root_money=self._money_screen(section),
            )

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

    def _fill_inputs(self, screen: CrawlScreen, valid: bool = True) -> bool:
        """Type into each text field on the screen, then dismiss the keyboard.

        With ``valid`` (the default) it types realistic data so form-gated flows
        become reachable — a tap-only crawl stalls at any screen that gates
        progress behind text entry (login, exchange amount, search). With
        ``valid=False`` it types deliberately-invalid data to exercise the
        validation-error branch; fields with no meaningful invalid value are left
        blank. Returns whether it typed into at least one field.
        """
        # Imported lazily: classify imports CrawlElement from this module, so a
        # top-level import would be a circular import at load time.
        from framework.crawler.classify import classify

        typed = False
        for element in screen.elements:
            if not self._own(element) or classify(element)[0] != "input":
                continue
            value = _sample_value(element) if valid else _invalid_value(element)
            if not value:
                continue  # nothing meaningful to type (invalid-mode, untyped field)
            try:
                self.driver.tap(*element.center)
                self.driver.type_text(value)
                typed = True
            except Exception:  # a field that won't accept input must not abort the crawl
                continue
        if typed:
            hide = getattr(self.driver, "hide_keyboard", None)
            if callable(hide):
                try:
                    hide()
                except Exception:
                    pass
        return typed

    def _submit_control(self, screen: CrawlScreen) -> Optional[CrawlElement]:
        """The button on this screen that commits a form (login/continue/…), or
        None. Skips blocked controls so a probe never taps Pay/Buy/Delete."""
        from framework.crawler.classify import classify

        money = self._money_screen(screen)
        for element in screen.interactive():
            if not self._own(element) or self._blocked(element, money_context=money):
                continue
            if classify(element)[0] != "button":
                continue
            label = element.label.strip().lower()
            if any(k in label for k in _SUBMIT_LABELS):
                return element
        return None

    def _has_input(self, screen: CrawlScreen) -> bool:
        from framework.crawler.classify import classify

        return any(self._own(e) and classify(e)[0] == "input" for e in screen.elements)

    def _handle_form(self, result: CrawlResult, screen: CrawlScreen) -> None:
        """Exercise a form both ways. First probe the *negative* branch (invalid
        input → submit → the app should reject it), so the validation-error state
        is discovered; then fill *valid* data so the depth-first walk drives the
        *positive* branch. Covering both is how the generated suite catches
        validation defects instead of only happy paths."""
        self._probe_negative_form(result, screen)
        self._fill_inputs(screen, valid=True)

    def _probe_negative_form(self, result: CrawlResult, screen: CrawlScreen) -> None:
        """Fill a form with invalid data and submit once, recording the outcome as
        a real discovered state — the error screen if the app rejects it, or the
        next screen if it wrongly advances (that *is* the validation bug). Bounded
        to once per form and always returns to the form for the positive branch."""
        if screen.fingerprint in self._neg_probed:
            return
        submit = self._submit_control(screen)
        if submit is None or not self._has_input(screen):
            return  # not a submittable form
        self._neg_probed.add(screen.fingerprint)
        if not self._fill_inputs(screen, valid=False):
            return  # no strongly-typed field to make invalid — nothing to probe
        try:
            self.driver.tap(*submit.center)
        except Exception:
            return
        result.steps += 1
        if not self._on_app():  # a probe must never strand the crawl off the app
            self._recover()
            return
        outcome = self._read_content_screen()
        if not outcome.fingerprint:
            return
        result.transitions.append(Transition(screen.fingerprint, submit, outcome.fingerprint, kind="probe"))
        if outcome.fingerprint != screen.fingerprint:
            result.screens.setdefault(outcome.fingerprint, outcome)  # error / next state
            self._note_screen(result, outcome.fingerprint)
            self._go_back(screen.fingerprint)  # back to the form for the positive branch

    def _within_budget(self, result: CrawlResult) -> bool:
        """All three budgets: the step count, the wall clock (when set), and the
        novelty plateau (when set). Checked at every loop boundary so a slow device
        caps total run time and a saturated crawl stops instead of re-treading."""
        if result.steps >= self.max_steps or time.monotonic() >= self._deadline:
            return False
        # Re-anchor the plateau counter whenever the map grew a new screen template.
        if len(result.screens) > self._screens_high:
            self._screens_high = len(result.screens)
            self._step_at_last_new = result.steps
        if self.max_novelty_gap > 0 and result.steps - self._step_at_last_new >= self.max_novelty_gap:
            return False
        return True

    def _dfs(
        self,
        result: CrawlResult,
        root_fp: str,
        root_todo: Deque[CrawlElement],
        exclude_nav: bool = False,
        root_money: bool = False,
    ) -> None:
        """Depth-first walk from one root screen, tapping untried elements and
        backing out of dead ends. Shared by the single-root and per-tab crawls."""
        stack: List[_Frame] = [_Frame(root_fp, root_todo, {self._element_key(e) for e in root_todo}, money=root_money)]

        while stack and self._within_budget(result):
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
            if self._blocked(element, money_context=frame.money) or not self._own(element):
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

            result.transitions.append(Transition(current_fp, element, new_screen.fingerprint))

            if new_screen.fingerprint == current_fp:
                continue  # no navigation; keep trying elements on this screen

            # Pass a gate on this screen — a login/OTP/biometric step, OR a gate
            # that *re-appears* mid-crawl (a session expiring drops us back on
            # login). Firing here, before the seen/new split (bounded re-fire in
            # _pass_gates), is what makes re-auth work: a re-appearing login is
            # passed again, not written off as "already seen".
            if self._pass_gates(new_screen):
                behind = self._read_content_screen()
                if behind.fingerprint and behind.fingerprint != new_screen.fingerprint:
                    result.transitions.append(Transition(new_screen.fingerprint, element, behind.fingerprint))
                    result.screens.setdefault(behind.fingerprint, behind)
                    self._note_screen(result, behind.fingerprint)
                    new_screen = behind

            if new_screen.fingerprint not in result.screens and len(stack) < self.max_depth:
                result.screens[new_screen.fingerprint] = new_screen
                self._note_screen(result, new_screen.fingerprint)
                # A terminal obstacle (paywall / update wall / CAPTCHA) is mapped
                # but never explored — don't tap Subscribe/Update (spends money /
                # leaves the app) or loop on a challenge we must not solve; record
                # it and back out to the parent.
                if terminal_obstacle(new_screen) is not None:
                    result.steps += 1
                    self._go_back(current_fp)
                    continue
                self._handle_form(result, new_screen)  # exercise its form both ways (invalid→error, valid)
                child = self._own_interactive(new_screen, exclude_nav=exclude_nav)
                stack.append(
                    _Frame(
                        new_screen.fingerprint,
                        child,
                        {self._element_key(e) for e in child},
                        money=self._money_screen(new_screen),
                    )
                )
            else:
                # Already seen (or depth cap): don't re-explore, return to parent.
                result.steps += 1
                self._go_back(current_fp)
