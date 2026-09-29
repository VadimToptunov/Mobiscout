"""
Language-agnostic test-framework model — the shape every Page-Object renderer shares.

A crawl becomes what a senior automation engineer would hand-write:

* **pages** — one per screen: private ranked locators, intention methods
  (``tap_sign_in()`` returning the page it opens, ``enter_email(value)`` returning
  itself), queries only where a test needs them, and an *identity* element that proves
  the page is on screen (distinctive to that page, never shared chrome like a logo);
* **scenarios** — tests expressed as calls on those pages, not raw locators, grouped by
  the screen they are about.

Each language renderer (Python today; Java/Kotlin/JS/C# next) turns this into its own
idiomatic layout: a BasePage with the shared plumbing, one page class per screen, a
driver fixture/base test, and test modules that read like intent.
"""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from framework.codegen.emitters._naming import pascal, snake
from framework.codegen.ir import ActionType, AssertionType, Platform, Selector, TestModel
from framework.crawler.models import CrawlElement, CrawlResult
from framework.crawler.to_codegen import _ASSERTABLE_SCORE, _looks_verbose, _owned, _title_element, selector_for

# Page stems a renderer already uses for its own classes (BasePage / base_page).
_RESERVED_STEMS = {"Base"}

# classify() types a user taps (inputs are typed into instead).
_TAP_TYPES = {"button", "checkbox", "switch", "radio"}


@dataclass
class ElementDef:
    """One located element on a page."""

    key: str  # snake_case, unique within the page — the stem of its method names
    selector: Selector  # ranked: primary + self-healing fallbacks
    role: str  # "tap" | "input" | "text"
    label: str = ""  # the crawl label, for distinctiveness checks
    navigates_to: Optional[str] = None  # page name a tap on it opens (from the crawl)


@dataclass
class PageDef:
    """One screen as a page object."""

    name: str  # PascalCase stem, unique — the class is ``{name}Page``
    title: str  # human-readable screen title for docs
    elements: List[ElementDef] = field(default_factory=list)
    identity: Optional[str] = None  # element key whose presence proves this page is on screen
    fingerprint: str = ""
    # Queries scenarios actually call ("has"/"lacks"/"text"/"enabled", key) — rendered on
    # demand so pages stay lean instead of growing a getter per label.
    queries: Set[Tuple[str, str]] = field(default_factory=set)

    @property
    def class_name(self) -> str:
        """The page class name (``LoginPage``)."""
        return f"{self.name}Page"

    def element(self, key: str) -> ElementDef:
        """The element with this key."""
        return next(e for e in self.elements if e.key == key)


@dataclass
class Call:
    """One step of a scenario, as a call on a page."""

    page: str  # PageDef.name
    op: str  # "tap" | "enter" | "is_displayed" | "has" | "lacks" | "text_is" | "is_enabled"
    element: Optional[str] = None
    value: Optional[str] = None


@dataclass
class Scenario:
    """One test, as a sequence of page calls."""

    name: str  # snake_case, unique
    description: str
    calls: List[Call]
    group: str  # the page this scenario is about — its test module


@dataclass
class FrameworkModel:
    """Everything a renderer needs to write a Page-Object framework."""

    app_package: str
    app_activity: Optional[str]
    platform: Platform
    launch_args: List[str]
    pages: List[PageDef]
    scenarios: List[Scenario]

    def page(self, name: str) -> PageDef:
        """The page with this name."""
        return next(p for p in self.pages if p.name == name)


def _sentence(text: str) -> str:
    """A description as a sentence — capitalised, ending in a full stop — so generated
    docstrings / Javadoc read like prose, not fragments."""
    text = " ".join((text or "").split())
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?" else f"{text}."


def _sel_key(selector: Selector) -> Tuple[str, str]:
    """Links a model step to a page element: both come from ``selector_for`` on the same
    crawl elements, so the primary locator's (strategy, value) matches on both sides."""
    return (selector.strategy.value, selector.value)


def _label(e: CrawlElement) -> str:
    """The element's crawl label (content-desc, text or id)."""
    return (e.content_desc or e.text or e.resource_id or "").strip()


def _element_key(e: CrawlElement) -> str:
    """A readable, valid identifier stem for an element's methods (``sign_in`` ->
    ``tap_sign_in``). A paragraph is never a name — it becomes ``description``."""
    rid = e.resource_id.split("/")[-1] if e.resource_id else ""
    raw = (e.content_desc or e.text or rid or e.class_name.split(".")[-1] or "").strip()
    if _looks_verbose(raw):
        raw = rid or ("description" if not e.clickable else e.class_name.split(".")[-1])
    name = re.sub(r"_+", "_", re.sub(r"[^0-9a-zA-Z_]", "_", snake(raw))).strip("_")[:30].strip("_")
    if not name:
        name = "element"
    if name[0].isdigit():
        name = f"e_{name}"
    if keyword.iskeyword(name):
        name = f"{name}_"
    return name


def _role(e: CrawlElement) -> str:
    """How a test uses the element: ``tap``, ``input`` or ``text``."""
    from framework.crawler.classify import classify

    kind = classify(e)[0]
    if kind == "input":
        return "input"
    if kind in _TAP_TYPES or e.clickable:
        return "tap"
    return "text"


def _pascal_ident(text: str) -> str:
    """A PascalCase identifier from free text (letters/digits only)."""
    return re.sub(r"[^0-9a-zA-Z]", "", pascal(text.strip()))[:40]


def _page_stem(index: int, owned: List[CrawlElement]) -> Tuple[str, str]:
    """(class stem, human title) from the screen's real title — not its first text, which
    is often a description paragraph. A control-only screen is named after its salient
    control; failing everything, ``Screen{N}``."""
    title_el = _title_element(owned)
    if title_el is not None:
        title = title_el.text.strip()
        stem = _pascal_ident(title)
        if stem and not stem[0].isdigit():
            return stem, title
    for e in owned:
        label = (e.label or "").strip()
        if e.clickable and label and not _looks_verbose(label):
            stem = _pascal_ident(label)
            if stem and not stem[0].isdigit():
                return stem, label
    return f"Screen{index}", f"Screen {index}"


def _build_pages(result: CrawlResult, app_package: str) -> Tuple[List[PageDef], Dict[str, PageDef]]:
    """One PageDef per screen with locatable elements, plus a fingerprint -> page map."""
    pages: List[PageDef] = []
    by_fp: Dict[str, PageDef] = {}
    stems: List[str] = []
    for i, (fp, screen) in enumerate(result.screens.items(), 1):
        owned = _owned(screen, app_package)
        elements: List[ElementDef] = []
        taken: Set[str] = set()
        for e in owned:
            sel = selector_for(e, owned, screen.platform)
            if sel is None:
                continue
            # Two elements sharing a label (a header and the button under it) must BOTH stay
            # drivable — dropping one silently deletes every step that targets it.
            base = _element_key(e)
            key, n = base, 2
            while key in taken:
                key, n = f"{base}_{n}", n + 1
            taken.add(key)
            elements.append(ElementDef(key=key, selector=sel, role=_role(e), label=_label(e)))
        if not elements:
            continue
        stem, title = _page_stem(i, owned)
        if stem in _RESERVED_STEMS:  # a screen titled "Base" must not shadow BasePage
            stem = f"{stem}Screen"
        if stem in stems:  # two screens titled the same -> AccountPage / Account2Page
            stem = f"{stem}{i}"
        stems.append(stem)
        page = PageDef(name=stem, title=title, elements=elements, fingerprint=fp)
        pages.append(page)
        by_fp[fp] = page

    # Identity: an element distinctive to this page across ALL pages (never shared chrome
    # such as a logo or app bar, which is on screen before a tap too — asserting it passes
    # even when the tap navigated nowhere). Prefer the page title; never rest on a
    # positional/fragile locator.
    labels = {p.name: {e.label for e in p.elements if e.label} for p in pages}
    for page in pages:
        others: Set[str] = set().union(*(labels[p.name] for p in pages if p is not page)) if len(pages) > 1 else set()
        distinctive = [
            e for e in page.elements if e.label and e.label not in others and e.selector.score >= _ASSERTABLE_SCORE
        ]
        titled = [e for e in distinctive if e.label == page.title]
        pool = titled or distinctive
        page.identity = pool[0].key if pool else None
    return pages, by_fp


def _wire_navigation(result: CrawlResult, app_package: str, by_fp: Dict[str, PageDef]) -> None:
    """Record, per tappable element, the page its tap opens — so ``tap_x()`` can return the
    next page object, the way a hand-written POM chains pages."""
    for from_fp, element, to_fp in result.transitions:
        src, dst = by_fp.get(from_fp), by_fp.get(to_fp)
        if src is None or dst is None or src is dst:
            continue
        screen = result.screens[from_fp]
        sel = selector_for(element, _owned(screen, app_package), screen.platform)
        if sel is None:
            continue
        for e in src.elements:
            if _sel_key(e.selector) == _sel_key(sel) and e.navigates_to is None:
                e.navigates_to = dst.name
                break


def _navigation_scenarios(pages: List[PageDef]) -> List[Scenario]:
    """From the entry page: tap each control that opens another page and prove arrival
    by that page's identity — a test with teeth (a tap that goes nowhere fails it)."""
    if not pages:
        return []
    entry = pages[0]
    out: List[Scenario] = []
    seen: Set[str] = set()
    for el in entry.elements:
        if el.navigates_to is None or el.key in seen:
            continue
        dst = next(p for p in pages if p.name == el.navigates_to)
        if dst.identity is None:
            continue
        seen.add(el.key)
        out.append(
            Scenario(
                name=f"{el.key}_opens_{snake(dst.name)}",
                description=f"On {entry.title}, tapping {el.label or el.key} opens {dst.title}.",
                calls=[Call(entry.name, "tap", el.key), Call(dst.name, "is_displayed")],
                group=dst.name,
            )
        )
    return out


def _flow_scenarios(model: TestModel, pages: List[PageDef]) -> List[Scenario]:
    """The IR's behavioural cases (screen state, journeys, form filling, negative input)
    as page calls. The current page is tracked through the steps, so an element that
    appears on several pages (a Back button) is resolved on the page actually on screen.

    A case is dropped rather than emitted broken: an interaction with no page element means
    its later assertions would check a screen the test never reached; a case left with no
    assertion would pass unconditionally under a name claiming it verified something."""
    if not pages:
        return []
    entry = pages[0]
    by_name = {p.name: p for p in pages}
    on_pages: Dict[Tuple[str, str], List[PageDef]] = {}
    for p in pages:
        for e in p.elements:
            on_pages.setdefault(_sel_key(e.selector), []).append(p)

    out: List[Scenario] = []
    for case in model.cases:
        current = entry
        last_asserted: Optional[PageDef] = None
        calls: List[Call] = []
        ok, asserted = True, False
        for step in case.steps:
            if step.action is ActionType.LAUNCH:
                current = entry
                continue
            if step.selector is None:
                continue  # waits / back / swipe: the page layer covers settling
            candidates = on_pages.get(_sel_key(step.selector), [])
            if not candidates:
                if step.action in (ActionType.TAP, ActionType.TYPE):
                    ok = False
                    break
                continue
            page = current if current in candidates else candidates[0]
            el = next(e for e in page.elements if _sel_key(e.selector) == _sel_key(step.selector))
            if step.action is ActionType.TAP:
                calls.append(Call(page.name, "tap", el.key))
                current = by_name.get(el.navigates_to or "", page)
            elif step.action is ActionType.TYPE:
                calls.append(Call(page.name, "enter", el.key, step.text or ""))
                current = page
            elif step.action is ActionType.ASSERT:
                asserted = True
                current = last_asserted = page
                if step.assertion is AssertionType.NOT_VISIBLE:
                    calls.append(Call(page.name, "lacks", el.key))
                elif step.assertion is AssertionType.TEXT_EQUALS and step.expected is not None:
                    calls.append(Call(page.name, "text_is", el.key, step.expected))
                elif step.assertion is AssertionType.ENABLED:
                    calls.append(Call(page.name, "is_enabled", el.key))
                elif el.key == page.identity:
                    calls.append(Call(page.name, "is_displayed"))
                else:
                    calls.append(Call(page.name, "has", el.key))
        if not ok or not asserted:
            continue
        calls = _still_here(calls, by_name)
        out.append(
            Scenario(
                name=snake(case.name) or "scenario",
                description=_sentence(case.description or case.name),
                calls=calls,
                group=(last_asserted or current).name,
            )
        )
    return out


def _still_here(calls: List[Call], by_name: Dict[str, PageDef]) -> List[Call]:
    """ "The control I just tapped is still shown" means "the tap did not leave this screen"
    (a rejected form) — so prove it by the page's identity. The control itself proves
    nothing: the next screen of a wizard has an identical Continue, so the check would pass
    even when the app accepted invalid input and moved on."""
    out: List[Call] = []
    for i, c in enumerate(calls):
        prev = calls[i - 1] if i else None
        stays = prev is not None and prev.op == "tap" and (prev.page, prev.element) == (c.page, c.element)
        if c.op == "has" and stays and by_name[c.page].identity is not None:
            out.append(Call(c.page, "is_displayed"))
        else:
            out.append(c)
    return out


def build_framework_model(result: CrawlResult, model: TestModel, app_package: str) -> FrameworkModel:
    """A crawl + its test model -> the language-agnostic Page-Object framework model."""
    pages, by_fp = _build_pages(result, app_package)
    _wire_navigation(result, app_package, by_fp)

    unique: List[Tuple[Scenario, tuple]] = []
    seen_sigs: Set[tuple] = set()
    for sc in _navigation_scenarios(pages) + _flow_scenarios(model, pages):
        sig = tuple((c.page, c.op, c.element, c.value) for c in sc.calls)
        if sig in seen_sigs:  # the same test reached two ways — keep one
            continue
        seen_sigs.add(sig)
        unique.append((sc, sig))

    # A scenario whose steps are a strict prefix of another's adds no coverage — the longer
    # one performs and checks all of it first — only run time. Drop it: a fast suite
    # doesn't repeat itself.
    scenarios: List[Scenario] = []
    used_names: Set[str] = set()
    for sc, sig in unique:
        if any(len(other) > len(sig) and other[: len(sig)] == sig for _, other in unique):
            continue
        name, n = sc.name, 2
        while name in used_names:
            name, n = f"{sc.name}_{n}", n + 1
        used_names.add(name)
        sc.name = name
        scenarios.append(sc)

    # Pages grow query methods only for what a scenario actually calls.
    kinds = {"has": "has", "lacks": "lacks", "text_is": "text", "is_enabled": "enabled"}
    by_name = {p.name: p for p in pages}
    for sc in scenarios:
        for c in sc.calls:
            if c.op in kinds and c.element is not None:
                by_name[c.page].queries.add((kinds[c.op], c.element))

    return FrameworkModel(
        app_package=app_package,
        app_activity=model.app_activity,
        platform=model.platform,
        launch_args=list(model.launch_args or []),
        pages=pages,
        scenarios=scenarios,
    )
