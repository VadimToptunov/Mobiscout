"""
Waypoints — teach the crawler to get *past* gates so it can explore behind them.

Autonomous crawling stops at gates: a login form, an OTP/TOTP prompt, a
permission dialog, a biometric check. A waypoint is a small instruction —
"when you reach a screen like this, do that to pass" — so the crawl reaches the
screens behind the gate and the graph/inventory cover the whole app, not just
its front door.

    Waypoint(when={"text_contains": "sign in"}, action="fill",
             data={"fields": {"email": "test@example.com", "password": "Pw123!"},
                   "submit": "Sign in"})

Matching is by screen content; the action is performed through the crawler
driver (tap + type_text) and the fixtures (TOTP, biometric). Kept deliberately
small and device-free-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from framework.crawler.app_crawler import CrawlElement, CrawlScreen


@dataclass
class Waypoint:
    """A gate-passing instruction. ``when`` matches a screen; ``action`` + ``data``
    say how to pass it."""

    when: Dict[str, Any]
    action: str  # fill | totp | grant | tap | biometric
    data: Dict[str, Any] = field(default_factory=dict)


def _haystack(element: CrawlElement) -> str:
    return f"{element.text} {element.content_desc} {element.resource_id}".lower()


def matches(waypoint: Waypoint, screen: CrawlScreen) -> bool:
    """Does this screen match the waypoint's ``when`` condition?

    Supported keys: ``text_contains`` (substring on any element), ``resource_id``
    (substring on any id), ``has_input`` (screen contains a text field)."""
    when = waypoint.when
    els = screen.elements
    if "text_contains" in when:
        needle = str(when["text_contains"]).lower()
        if not any(needle in _haystack(e) for e in els):
            return False
    if "resource_id" in when:
        rid = str(when["resource_id"]).lower()
        if not any(rid in (e.resource_id or "").lower() for e in els):
            return False
    if when.get("has_input"):
        if not any(_is_input(e) for e in els):
            return False
    return True


def _is_input(element: CrawlElement) -> bool:
    cls = element.class_name.lower()
    return any(k in cls for k in ("edittext", "textfield", "securetextfield", "searchfield"))


def _find(els: List[CrawlElement], hint: str, exclude_ids: Optional[set] = None) -> Optional[CrawlElement]:
    """First element whose text/desc/id mentions ``hint`` (case-insensitive),
    skipping any element whose ``id()`` is in ``exclude_ids`` (already consumed)."""
    h = hint.lower()
    skip = exclude_ids or set()
    return next((e for e in els if id(e) not in skip and h in _haystack(e)), None)


def _tap(driver: Any, element: CrawlElement) -> None:
    x, y = element.center
    driver.tap(x, y)


def apply(waypoint: Waypoint, driver: Any, screen: CrawlScreen) -> bool:
    """Perform the waypoint's action on the current screen via the driver/fixtures.
    Returns True if it did something (the crawler should then re-read the screen)."""
    els = screen.elements
    action = waypoint.action
    data = waypoint.data

    if action == "fill":
        return _fill(driver, els, data)
    if action == "totp":
        return _totp(driver, els, data)
    if action == "grant":
        target = _find(els, data.get("button", "allow"))
        if target is None:
            return False
        _tap(driver, target)
        return True
    if action == "tap":
        target = _find(els, data.get("target", ""))
        if target is None:
            return False
        _tap(driver, target)
        return True
    if action == "biometric":
        from framework.fixtures.biometric import pass_biometric

        pass_biometric(driver, platform=data.get("platform", "android"))
        return True
    return False


def _fill(driver: Any, els: List[CrawlElement], data: Dict[str, Any]) -> bool:
    """Fill inputs by field hint, then tap the form's submit control."""
    fields: Dict[str, str] = data.get("fields", {})
    inputs = [e for e in els if _is_input(e)]
    used_ids: set = set()  # inputs already filled — never reuse (so two unmatched
    # fields land in two different inputs instead of both overwriting inputs[0]).
    did = False
    last_input_y = 0
    for hint, value in fields.items():
        target = _find(inputs, hint, used_ids)
        if target is None:  # no hint match -> consume the next unused input positionally
            target = next((e for e in inputs if id(e) not in used_ids), None)
        if target is None:
            continue
        used_ids.add(id(target))
        if target.bounds:
            last_input_y = max(last_input_y, target.bounds[1])
        _tap(driver, target)
        if hasattr(driver, "type_text"):
            driver.type_text(value)
            did = True
    submit = _submit_button(els, data["submit"], last_input_y) if data.get("submit") else None
    if submit is not None:
        _tap(driver, submit)
        did = True
    return did


def _submit_button(els: List[CrawlElement], hint: str, after_y: int) -> Optional[CrawlElement]:
    """The form's submit control among elements matching ``hint``.

    A gate often repeats the same label on the launching screen and inside the
    form ("Log in" on the welcome screen AND on the sign-in form), so the *first*
    match is frequently the wrong one. Prefer a match that sits below the inputs we
    just filled (the form's own submit), then the lowest match on screen, so we tap
    the button that actually submits the form."""
    needle = str(hint).lower()
    cands = [e for e in els if needle in _haystack(e) and e.bounds]
    if not cands:
        return None
    below = [e for e in cands if e.bounds[1] >= after_y]
    return max(below or cands, key=lambda e: e.bounds[1])


def _totp(driver: Any, els: List[CrawlElement], data: Dict[str, Any]) -> bool:
    from framework.fixtures.totp import totp

    field_el = _find(els, data.get("field", "otp")) or _find(els, "code")
    if field_el is None or not hasattr(driver, "type_text"):
        return False
    _tap(driver, field_el)
    driver.type_text(totp(data["secret"]))
    submit = _find(els, data["submit"]) if data.get("submit") else None
    if submit is not None:
        _tap(driver, submit)
    return True


def apply_first_match(waypoints: List[Waypoint], driver: Any, screen: CrawlScreen) -> bool:
    """Apply the first waypoint that matches the screen; True if one fired."""
    for wp in waypoints or []:
        if matches(wp, screen):
            return bool(apply(wp, driver, screen))
    return False
