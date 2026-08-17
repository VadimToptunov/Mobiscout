"""
Bridge: crawler output -> codegen IR + audits.

Turns a CrawlResult into a comprehensive codegen TestModel (not just a smoke
suite): per-screen state checks, navigation/interaction flows from the recorded
transitions, plus a standalone accessibility audit. This is the
"explore -> automate" seam that closes the golden path:

    AppCrawler.crawl() -> CrawlResult -> build_test_model -> emitter -> test code
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Optional

from framework.codegen.ir import (
    ActionType,
    AssertionType,
    Platform,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen


def _auth_field_selector(hint: str, platform: str) -> Selector:
    """A best-effort locator for a login/gate input by its hint (username / password
    / code) — an id/label/text substring match, the same fuzz the crawl used. Low
    score: it's a generated-auth convenience, flagged fragile for a human to firm up."""
    h = hint.strip()
    if platform == "ios":
        value = f"//*[contains(@name,'{h}') or contains(@label,'{h}') or contains(@value,'{h}')]"
    else:
        value = f"//*[contains(@resource-id,'{h}') or contains(@content-desc,'{h}') or contains(@text,'{h}')]"
    return Selector(SelectorStrategy.XPATH, value, score=0.4, description=f"{h} field")


def waypoints_to_steps(waypoints: Optional[List[Any]], platform: str = "android") -> List[Step]:
    """Turn the crawl's gate-passing waypoints (login / OTP / passcode / permission)
    into IR steps, so a generated test reproduces the auth a behind-it screen needs
    to be reached — without it, that test just stalls on the login. Accepts waypoint
    dicts (from config) or Waypoint objects."""
    steps: List[Step] = []
    for wp in waypoints or []:
        action = wp.get("action") if isinstance(wp, dict) else getattr(wp, "action", None)
        data = (wp.get("data") if isinstance(wp, dict) else getattr(wp, "data", None)) or {}
        if action == "fill":
            for hint, value in (data.get("fields") or {}).items():
                steps.append(
                    Step(
                        ActionType.TYPE,
                        selector=_auth_field_selector(str(hint), platform),
                        text=str(value),
                        description=f"Enter {hint}",
                    )
                )
            submit = data.get("submit")
            if submit:
                steps.append(
                    Step(
                        ActionType.TAP,
                        selector=Selector(SelectorStrategy.TEXT, str(submit), description="submit"),
                        description=f"Tap {submit}",
                    )
                )
        elif action in ("tap", "grant"):
            target = data.get("target") or data.get("button") or "Allow"
            steps.append(
                Step(ActionType.TAP, selector=Selector(SelectorStrategy.TEXT, str(target)), description=f"Tap {target}")
            )
    return steps


if TYPE_CHECKING:
    from framework.crawler.graph import InteractionGraph


def _looks_dynamic(text: str) -> bool:
    """Whether a visible-text value looks run-to-run *unstable* — so a locator
    built from it is fragile and should score lower. Harvested from the former
    ``selectors.selector_scorer``: flags multi-digit runs (counts, ids, times),
    currency amounts, and very short strings (often generated/opaque)."""
    if re.search(r"\d{2,}", text):
        return True
    if any(symbol in text for symbol in ("$", "€", "£", "¥")):
        return True
    return len(text.strip()) < 3


def _xpath_by_label(value: str) -> str:
    """An iOS-safe XPath that locates an element by its visible label / name.
    Quote-safe: uses whichever quote the value lacks, or concat() if it has both."""
    if '"' not in value:
        lit = f'"{value}"'
    elif "'" not in value:
        lit = f"'{value}'"
    else:  # contains both quote kinds — build a concat() literal
        pieces = value.split('"')
        lit = "concat(" + ", '\"', ".join(f'"{p}"' for p in pieces) + ")"
    return f"//*[@label={lit} or @name={lit}]"


def _selector_for(element: CrawlElement, platform: str = "android") -> Optional[Selector]:
    """Ranked IR selector (primary + fallbacks) from a crawled element.

    Accessibility-id and resource-id map identically on both platforms, but a
    *visible-text* locator does not: Android wants a uiautomator ``text()``
    selector, whereas iOS has no such thing — it must match the element's
    ``label`` via XPath. So the text tier is rendered per platform.
    """
    candidates: List[Selector] = []
    label = element.label
    if platform == "ios":
        # iOS field semantics (see parse._ios_element): the accessibility
        # IDENTIFIER lives in `resource_id` and is what Appium's accessibility-id
        # strategy matches (the element's `name`), so it is the primary locator.
        # The human-visible accessibility LABEL (`content_desc`) / `value` (`text`)
        # has no dedicated selector on iOS — it is matched by XPath on @label/@name.
        ident = (element.resource_id or "").strip()
        if ident:
            candidates.append(Selector(SelectorStrategy.ACCESSIBILITY_ID, ident, score=0.95, description=label))
        vis = (element.content_desc or element.text or "").strip()
        if vis:
            text_score = 0.42 if _looks_dynamic(vis) else 0.60
            candidates.append(
                Selector(SelectorStrategy.XPATH, _xpath_by_label(vis), score=text_score, description=label)
            )
    else:
        cd = (element.content_desc or "").strip()
        if cd:
            candidates.append(Selector(SelectorStrategy.ACCESSIBILITY_ID, cd, score=0.95, description=label))
        rid = (element.resource_id or "").strip()
        if rid:
            candidates.append(Selector(SelectorStrategy.ID, rid, score=0.90, description=label))
        txt = (element.text or "").strip()
        if txt:
            # A text locator is already the least-stable tier; if the text itself
            # looks dynamic (a count, price, timestamp) it is more fragile still, so
            # score it lower. Order is unchanged — text stays last — this only makes
            # the stability score honest for the inventory / model-path ranking.
            text_score = 0.42 if _looks_dynamic(txt) else 0.60
            candidates.append(Selector(SelectorStrategy.TEXT, txt, score=text_score, description=label))
    if not candidates:
        return None
    primary, *rest = candidates
    primary.fallbacks = rest
    return primary


def _contains(outer: CrawlElement, inner: CrawlElement) -> bool:
    ox1, oy1, ox2, oy2 = outer.bounds
    ix1, iy1, ix2, iy2 = inner.bounds
    return ox1 <= ix1 and oy1 <= iy1 and ix2 <= ox2 and iy2 <= oy2 and inner.bounds != outer.bounds


def _structural_selector(
    element: CrawlElement, siblings: List[CrawlElement], platform: str
) -> Optional[Selector]:
    """A last-resort positional locator — the Nth element of its class on screen —
    for a control with no id/label/text at all (an icon button, an image). Fragile
    (score 0.3, flagged) and never good enough to assert on, but it keeps an
    otherwise-unlocatable element *tappable*, so navigation through it is still
    generated instead of dropped."""
    cls = (element.class_name or "").strip()
    if not cls:
        return None
    same = [e for e in siblings if e.class_name == cls]
    index = next((i for i, e in enumerate(same) if e is element), None)
    if index is None:
        return None
    tag = f"XCUIElementType{cls}" if platform == "ios" else cls
    return Selector(SelectorStrategy.XPATH, f"(//{tag})[{index + 1}]", score=0.3, description=cls)


def selector_for(
    element: CrawlElement, siblings: Optional[List[CrawlElement]] = None, platform: str = "android"
) -> Optional[Selector]:
    """Locator for an element, with a Jetpack Compose fallback and a positional
    last resort.

    In Compose the clickable node is often an unlabelled wrapper while the
    visible text sits on a non-clickable child, so a direct locator is empty.
    When that happens for a clickable element, borrow the locator of the
    innermost labelled element contained within its bounds — tapping that child
    (inside the clickable) triggers the same action. If even that finds nothing
    (a truly label-less icon), fall back to a positional locator so the control is
    still reachable.
    """
    own = _selector_for(element, platform)
    if own is not None or not element.clickable or not siblings:
        return own
    best: Optional[Selector] = None
    best_area: Optional[int] = None
    for other in siblings:
        if other is element or not _contains(element, other):
            continue
        sel = _selector_for(other, platform)
        if sel is None:
            continue
        x1, y1, x2, y2 = other.bounds
        area = (x2 - x1) * (y2 - y1)
        if best_area is None or area < best_area:
            best, best_area = sel, area
    if best is not None:
        return best
    return _structural_selector(element, siblings, platform)


def _owned(screen: CrawlScreen, app_package: str) -> List[CrawlElement]:
    return [e for e in screen.elements if e.package in ("", app_package)]


# Semantic types worth asserting on a screen — the things a user acts on. Static
# text, images, prices and decoration are left to the inventory, not the tests.
_MEANINGFUL_TYPES = {"button", "input", "checkbox", "switch", "radio"}
_MAX_SCREEN_ELEMENTS = 8


def _slug(text: str, max_len: int = 32) -> str:
    """A short, human, identifier-safe token from a label — so generated test names
    read like sentences: 'See all' -> 'see_all', 'Markets' -> 'markets'. Pure-number
    / symbol-only labels ('€1,204.55') yield '' (they don't name anything)."""
    words = [w for w in re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).split("_") if w and not w.isdigit()]
    return "_".join(words)[:max_len].strip("_")


def _screen_title(owned: List[CrawlElement]) -> str:
    """The screen's title landmark text (the first meaningful static text), used to
    name a screen readably ('Markets' -> markets_screen)."""
    from framework.crawler.classify import classify

    for e in owned:
        if classify(e)[0] == "text" and (e.text or "").strip():
            return e.text.strip()
    return ""


def _unique(name: str, used: set) -> str:
    """Ensure a case name is unique, appending _2, _3… on collision."""
    candidate, n = name, 2
    while candidate in used:
        candidate = f"{name}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def _significant(owned: List[CrawlElement]) -> List[CrawlElement]:
    """The elements worth a state assertion: one title landmark (so the screen is
    identifiable) plus the actionable elements — not every label."""
    from framework.crawler.classify import classify

    landmark = None
    actionable: List[CrawlElement] = []
    for e in owned:
        etype = classify(e)[0]
        if etype in _MEANINGFUL_TYPES:
            actionable.append(e)
        elif etype == "text" and landmark is None and (e.text or "").strip():
            landmark = e
    return ([landmark] if landmark else []) + actionable[:_MAX_SCREEN_ELEMENTS]


def _value_elements(owned: List[CrawlElement]) -> List[CrawlElement]:
    """The static text *values* worth pinning with a TEXT_EQUALS assertion.

    These are the displayed values a behavioural defect would corrupt — a money
    amount that rounds wrong, a P&L that flips sign, a validation message with the
    wrong text. They are precisely the static-text elements the VISIBLE-only path
    leaves to the inventory (``_significant`` drops them as decoration).

    Criteria: a text-type element (not an interactive control being tapped) whose
    text carries at least two non-whitespace characters. Deliberately *not* gated
    on :func:`_looks_dynamic`: money/counts look 'dynamic' but are exactly the
    thing to pin. Only empty/whitespace/single-char values are skipped.
    """
    from framework.crawler.classify import classify

    values: List[CrawlElement] = []
    for e in owned:
        text = (e.text or "").strip()
        if len(text) < 2:
            continue
        if classify(e)[0] != "text":
            continue  # not purely a control/interactive label being tapped
        values.append(e)
    return values


def _screen_cases(
    index: int,
    screen: CrawlScreen,
    app_package: str,
    nav_prefix: Optional[List[Step]] = None,
    assert_values: bool = False,
    auth_prefix: Optional[List[Step]] = None,
) -> Optional[TestCase]:
    """A per-screen state case — meaningful, not exhaustive: assert the screen's
    landmark and its actionable elements (buttons/inputs/…), not every label.

    ``nav_prefix`` are the TAP steps that reach this screen from the entry (empty
    for the entry screen). They run after launch so the assertions are made on the
    right screen, not a bare launch.

    When ``assert_values`` is True, ALSO pin the observed text of stable static
    values (TEXT_EQUALS) on top of the VISIBLE checks, so a defect that changes a
    displayed value makes the test fail. Off by default (byte-identical output)."""
    steps: List[Step] = [Step(ActionType.LAUNCH, description="Open app")]
    if auth_prefix:
        steps.extend(auth_prefix)  # pass the gate(s) before navigating/asserting
    if nav_prefix:
        steps.extend(nav_prefix)
    seen = set()
    owned = _owned(screen, app_package)
    for element in _significant(owned):
        selector = selector_for(element, owned, screen.platform)
        if selector is None or selector.value in seen:
            continue
        # Don't assert on an element whose only locator is a fragile dynamic/short
        # text (score < 0.5, e.g. a bare "0"/"1" value): it flakes and isn't a
        # dependable state check. Such elements are still tappable for navigation.
        if selector.score < 0.5:
            continue
        seen.add(selector.value)
        label = element.label or element.class_name
        steps.append(
            Step(
                ActionType.ASSERT, selector=selector, assertion=AssertionType.VISIBLE, description=f"{label} is visible"
            )
        )
        if element.clickable:
            steps.append(
                Step(
                    ActionType.ASSERT,
                    selector=selector,
                    assertion=AssertionType.ENABLED,
                    description=f"{label} is enabled",
                )
            )
    if assert_values:
        # Opt-in: pin observed values. Independent of the VISIBLE pass above — a
        # static value (a price, a P&L) is decoration to _significant but is the
        # very thing a behavioural defect corrupts. Dedup on locator so we don't
        # pin the same element twice (e.g. a value that is also the landmark).
        pinned = set()
        for element in _value_elements(owned):
            selector = selector_for(element, owned, screen.platform)
            if selector is None or selector.value in pinned:
                continue
            pinned.add(selector.value)
            label = element.label or element.class_name
            steps.append(
                Step(
                    ActionType.ASSERT,
                    selector=selector,
                    assertion=AssertionType.TEXT_EQUALS,
                    expected=element.text,
                    description=f"{label} shows {element.text.strip()!r}",
                )
            )
    if not any(step.action == ActionType.ASSERT for step in steps):
        return None
    title = _slug(_screen_title(owned))
    name = f"{title}_screen_shows_expected_controls" if title else f"screen_{index + 1}_shows_expected_controls"
    human = title.replace("_", " ") if title else f"screen {index + 1}"
    return TestCase(name=name, steps=steps, description=f"The {human} screen shows its expected controls")


def _navigation_cases(result: CrawlResult, app_package: str) -> List[TestCase]:
    """Functional flows: from the start screen, tap an element and assert we
    reached the destination screen (a distinctive element there is visible)."""
    if not result.screens:
        return []
    start_fp = next(iter(result.screens))
    cases: List[TestCase] = []
    seen_taps = set()
    from_screen = result.screens.get(start_fp)
    from_elements = _owned(from_screen, app_package) if from_screen else []
    from_platform = from_screen.platform if from_screen else "android"
    for from_fp, element, to_fp in result.transitions:
        if from_fp != start_fp or to_fp == start_fp:
            continue  # only depth-1, real navigations (path reconstruction is future work)
        tap = selector_for(element, from_elements, from_platform)
        if tap is None or tap.value in seen_taps:
            continue
        target = result.screens.get(to_fp)
        target_elements = _owned(target, app_package) if target else []
        target_platform = target.platform if target else "android"
        # Prefer a landmark that is *distinctive* to the destination — one whose
        # identity isn't also on the start screen — so the assertion proves we
        # actually navigated, not that shared chrome (a tab bar, a header) is still
        # on screen. Fall back to any locatable element if nothing is unique.
        start_keys = {(e.content_desc or e.text or e.resource_id) for e in from_elements}

        def _distinctive(e: "CrawlElement") -> bool:
            key = e.content_desc or e.text or e.resource_id
            return bool(key) and key not in start_keys

        ranked_targets = sorted(target_elements, key=lambda e: 0 if _distinctive(e) else 1)
        landmark = next(
            (s for s in (selector_for(e, target_elements, target_platform) for e in ranked_targets) if s), None
        )
        if landmark is None:
            continue
        seen_taps.add(tap.value)
        tapped = element.label or element.class_name
        # Name the test after what it does: tap <control> -> reach <destination>.
        tap_slug = _slug(tapped) or "control"
        dest_slug = _slug(_screen_title(target_elements)) or _slug(landmark.description or "") or "the_next_screen"
        steps = [
            Step(ActionType.LAUNCH, description="Open app"),
            Step(ActionType.TAP, selector=tap, description=f"Tap {tapped}"),
            Step(
                ActionType.ASSERT,
                selector=landmark,
                assertion=AssertionType.VISIBLE,
                description="Destination screen is shown",
            ),
        ]
        cases.append(
            TestCase(
                name=f"tapping_{tap_slug}_opens_{dest_slug}",
                steps=steps,
                description=f"Tapping {tapped} opens the {dest_slug.replace('_', ' ')} screen",
            )
        )
    return cases


def build_test_model(
    result: CrawlResult,
    app_package: str,
    suite_name: str = "CrawlFlow",
    app_activity: Optional[str] = None,
    launch_args: Optional[List[str]] = None,
    graph: Optional["InteractionGraph"] = None,
    assert_values: bool = False,
    waypoints: Optional[List[Any]] = None,
) -> TestModel:
    """Comprehensive TestModel from a crawl: per-screen state checks (visible +
    enabled) plus navigation flows from the recorded transitions.

    ``launch_args`` are the app launch arguments the crawl used (e.g. to skip a
    login gate); they're carried into the generated driver setup so the tests
    start in the same state.

    ``graph`` may be a pre-built interaction graph for this same crawl. The graph
    is otherwise rebuilt several times over (once each by navigation_steps,
    multi_step_cases and negative_form_cases); passing it in builds it once and
    threads it through. It is deterministic for a given result/package, so the
    generated model is byte-for-byte identical whether or not it is supplied.

    ``assert_values`` (opt-in, default False) additionally pins observed static
    text values in the per-screen state cases via TEXT_EQUALS, so a defect that
    changes a displayed value fails the test. Default False keeps the generated
    output byte-identical to the VISIBLE-only path."""
    # Navigation prefixes per screen (lazy import: graph.py imports this module).
    # Screens with no path from the entry are omitted — unreachable, so not
    # state-testable; this also fixes state checks asserting a deeper screen's
    # controls right after a bare launch.
    from framework.crawler.graph import build_graph, multi_step_cases, navigation_steps

    graph = graph if graph is not None else build_graph(result, app_package)
    nav = navigation_steps(result, app_package, graph=graph)

    # Auth steps (login/OTP/passcode) reproduced from the waypoints, prepended to the
    # cases for screens the crawl reached only past a gate — so those tests can get
    # there instead of stalling on the login. Empty when no waypoints, so a
    # gate-free crawl's output is byte-identical.
    platform_str = next(iter(result.screens.values())).platform if result.screens else "android"
    auth_steps = waypoints_to_steps(waypoints, platform_str)

    cases: List[TestCase] = []
    for index, screen in enumerate(result.screens.values()):
        if screen.fingerprint not in nav:
            continue
        auth = auth_steps if (auth_steps and screen.fingerprint in result.gated) else None
        case = _screen_cases(
            index,
            screen,
            app_package,
            nav_prefix=nav[screen.fingerprint],
            assert_values=assert_values,
            auth_prefix=auth,
        )
        if case is not None:
            cases.append(case)
    cases.extend(_navigation_cases(result, app_package))

    # Multi-step, model-based paths through the interaction graph.
    cases.extend(multi_step_cases(result, app_package, graph=graph))

    # Negative-path coverage needs graph.negative_form_cases (lazy import:
    # graph.py imports this module, so importing here avoids a cycle).
    from framework.crawler.graph import negative_form_cases

    # Negative-path coverage: submit each form with invalid data and assert it is
    # rejected — the counterpart to the valid-data filling multi_step_cases does,
    # so both branches of every form are exercised.
    cases.extend(negative_form_cases(result, app_package, graph=graph))

    # Human-readable names can collide (two screens titled the same, two taps on
    # the same control) — keep every test method name unique.
    used: set = set()
    for case in cases:
        case.name = _unique(case.name, used)

    # The suite's platform follows the crawled screens (any iOS screen -> iOS),
    # so the emitters pick the right Appium client and text locators.
    is_ios = any(s.platform == "ios" for s in result.screens.values())

    # UI toolkit drives locator caveats (Compose/Flutter/WebView locate differently).
    # A non-native toolkit anywhere wins, since it changes how the tester must locate.
    toolkits = {s.toolkit for s in result.screens.values()}
    toolkit = next((t for t in ("flutter", "hybrid", "compose") if t in toolkits), "native")

    return TestModel(
        name=suite_name,
        app_package=app_package,
        platform=Platform.IOS if is_ios else Platform.ANDROID,
        app_activity=app_activity,
        cases=cases,
        description="Auto-generated from an autonomous crawl (state + navigation).",
        toolkit=toolkit,
        launch_args=list(launch_args or []),
    )


@dataclass
class AccessibilityFinding:
    screen_index: int
    class_name: str
    bounds: str
    issue: str


def audit_accessibility(result: CrawlResult, app_package: str = "") -> List[AccessibilityFinding]:
    """Flag interactive elements a screen reader cannot announce: clickable with
    no accessible label (no content-desc / text / resource-id)."""
    findings: List[AccessibilityFinding] = []
    for index, screen in enumerate(result.screens.values()):
        for element in _owned(screen, app_package) if app_package else screen.elements:
            if not element.clickable:
                continue
            has_label = element.content_desc or element.text or element.resource_id
            if not has_label:
                findings.append(
                    AccessibilityFinding(
                        screen_index=index + 1,
                        class_name=element.class_name,
                        bounds=str(element.bounds),
                        issue="clickable element has no accessible label (content-desc/text/id)",
                    )
                )
    return findings
