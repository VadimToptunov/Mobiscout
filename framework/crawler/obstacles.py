"""
Built-in obstacle handlers — auto-pass the common no-input screens that block an
autonomous crawl, with no configuration.

Unlike waypoints (user-supplied gate instructions that need *data* — credentials,
an OTP secret), an obstacle is recognised structurally and handled with a safe,
fixed action:

  * **non-terminal** — dismiss it and carry on: an onboarding/tutorial carousel,
    a cookie/consent banner (declined privacy-first), a rate-us / "enable
    notifications" / promo nag. :func:`clear_obstacle` taps a safe control and
    returns its name so the caller re-reads the screen.
  * **terminal** — a dead-end to map but never poke: an update wall, a paywall, a
    CAPTCHA / anti-bot check. :func:`terminal_obstacle` names it so the crawler
    records the screen and backs out instead of tapping "Update"/"Subscribe"
    (which leaves the app or spends money) or looping on a challenge it must not
    solve.

Matching is pure and device-free (unit tested); only :func:`clear_obstacle`
touches the driver.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from framework.crawler.models import CrawlElement, CrawlScreen

# --- non-terminal obstacles: signal words on the screen + a safe control to tap.

# Cookie/consent banners. Decline is preferred (privacy-first); accept is the
# fallback only so the crawl isn't stuck behind a mandatory banner.
_CONSENT_WORDS = ("cookie", "consent", "gdpr", "we use cookies", "we value your privacy", "your privacy", "tracking")
_CONSENT_DECLINE = ("reject all", "reject", "decline", "only necessary", "necessary only", "essential only", "no thanks")
_CONSENT_ACCEPT = ("accept all", "accept", "agree", "allow all", "i agree", "got it")

# Onboarding / tutorial carousels. Fire only on an explicit skip-like control so
# we never tap "Next"/"Continue" on a legitimate flow.
_ONBOARD_WORDS = ("welcome", "get started", "tutorial", "walkthrough", "tour", "swipe", "onboarding", "take a tour")
_ONBOARD_SKIP = ("skip", "get started", "let's go", "lets go", "start now", "done")

# Rate-us / promo / "enable notifications" nags — a dismiss control that keeps us
# in the app.
_NAG_WORDS = (
    "rate us", "rate this app", "rate app", "enjoying", "leave a review", "write a review",
    "special offer", "limited time", "enable notifications", "allow notifications", "turn on notifications",
)
_NAG_DISMISS = ("no thanks", "not now", "maybe later", "remind me later", "later", "no, thanks", "dismiss", "skip")

# --- terminal obstacles: dead-ends to record and back out of (never act on).

_CAPTCHA_WORDS = ("captcha", "recaptcha", "hcaptcha", "i'm not a robot", "i am not a robot", "verify you are human", "are you a robot")
_UPDATE_WORDS = ("update required", "please update", "update to continue", "must update", "update the app", "unsupported version", "outdated version")
_PAYWALL_WORDS = ("start free trial", "free trial", "subscribe", "unlock premium", "go premium", "upgrade to premium", "restore purchase", "per month", "per year")
# Root / jailbreak / emulator / integrity blocks — a hard dead-end the crawl can't
# (and shouldn't) get past; record it and move on rather than loop.
_INTEGRITY_WORDS = (
    "rooted device", "device is rooted", "jailbroken", "jailbreak detected", "device is not secure",
    "emulator is not supported", "cannot run on an emulator", "not supported on this device",
    "integrity check failed", "security check failed", "device not supported",
)

# --- transient errors: a flaky backend, not a real destination — retry, don't map.

_ERROR_WORDS = (
    "no internet", "no connection", "check your connection", "network error", "connection lost",
    "something went wrong", "server error", "unable to load", "failed to load", "request timed out",
    "try again later", "an error occurred",
)
_RETRY_LABELS = ("retry", "try again", "reload", "refresh")


def _blob(screen: CrawlScreen) -> str:
    return " ".join(f"{e.text} {e.content_desc}" for e in screen.elements).lower()


def _find(screen: CrawlScreen, needles: Iterable[str]) -> Optional[CrawlElement]:
    """The on-screen control whose visible label matches a needle, preferring the
    shortest label — a control reads "Retry" / "Reject all" / "Skip", while the
    same word buried in a sentence ("...please try again.") is body text we must
    not tap. Shortest-match picks the button, not the prose."""
    needles = tuple(needles)
    best: Optional[CrawlElement] = None
    best_len = 0
    for e in screen.elements:
        if not e.bounds:
            continue
        label = (e.text or e.content_desc or "").strip().lower()
        if label and any(n in label for n in needles):
            if best is None or len(label) < best_len:
                best = e
                best_len = len(label)
    return best


def clear_obstacle(driver: Any, screen: CrawlScreen) -> Optional[str]:
    """Dismiss one non-terminal obstacle on this screen by tapping a safe control.
    Returns the handler name if it acted (the caller should re-read the screen),
    else None. Ordered most- to least-specific so a consent banner isn't mistaken
    for a generic nag."""
    blob = _blob(screen)

    if any(w in blob for w in _CONSENT_WORDS):
        target = _find(screen, _CONSENT_DECLINE) or _find(screen, _CONSENT_ACCEPT)
        if target is not None:
            driver.tap(*target.center)
            return "consent"

    if any(w in blob for w in _ONBOARD_WORDS):
        target = _find(screen, _ONBOARD_SKIP)
        if target is not None:
            driver.tap(*target.center)
            return "onboarding"

    if any(w in blob for w in _NAG_WORDS):
        target = _find(screen, _NAG_DISMISS)
        if target is not None:
            driver.tap(*target.center)
            return "nag"

    return None


def terminal_obstacle(screen: CrawlScreen) -> Optional[str]:
    """Name a dead-end obstacle the crawler must record and back out of without
    acting on it — a CAPTCHA/anti-bot check (never solved, by policy), an update
    wall, a paywall (never purchased), or a root/emulator integrity block. None if
    the screen isn't one."""
    blob = _blob(screen)
    if any(w in blob for w in _CAPTCHA_WORDS):
        return "captcha"
    if any(w in blob for w in _INTEGRITY_WORDS):
        return "integrity_block"
    if any(w in blob for w in _UPDATE_WORDS):
        return "update_wall"
    if any(w in blob for w in _PAYWALL_WORDS):
        return "paywall"
    return None


def error_retry(driver: Any, screen: CrawlScreen) -> Optional[str]:
    """If the screen is a transient error (a flaky/offline backend — not a real
    destination) and offers a retry control, tap it and return "retry" so the
    caller re-reads. Bounded by the caller's loop, so a persistently-broken backend
    settles into the error screen being mapped once rather than looping forever.
    Returns None when there's no error, or an error with no retry control (that
    screen is a genuine state worth recording)."""
    blob = _blob(screen)
    if not any(w in blob for w in _ERROR_WORDS):
        return None
    target = _find(screen, _RETRY_LABELS)
    if target is None:
        return None
    driver.tap(*target.center)
    return "retry"
