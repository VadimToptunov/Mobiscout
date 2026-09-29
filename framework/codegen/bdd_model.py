"""
Language-agnostic BDD model, built on the Page-Object framework model.

What a senior writes when a suite is BDD — and what the old generic glue was not:

* **declarative features** — one per screen, in the user's words. Steps name what the user
  does and sees (``When I tap Sign in``, ``Then I see Product``), never a locator, and the
  incidental clicks that only *reach* a screen collapse into ``Given I am on the Catalog
  screen``;
* **thin, typed step definitions** — each step is one call on a page object (the page owns
  locating, waiting and self-healing), grouped by the page they drive; no generic
  ``I tap "{string}"`` step dispatching on a locator registry;
* **Background** for the precondition every scenario of a feature shares, and **Scenario
  Outline** only where scenarios genuinely differ in data alone.

Step texts are unique across the whole suite (Cucumber matches a step regardless of its
Given/When/Then keyword), and free of every character a step pattern treats as syntax in
any target language, so one feature file drives every renderer. A step's single parameter,
where it has one, is a quoted string written ``{string}`` here; each renderer turns that
into its own pattern syntax.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from framework.codegen.framework_model import Call, FrameworkModel, PageDef, Scenario, repeated

PARAM = "{string}"

#: Characters with pattern meaning somewhere — Cucumber expressions ( ) { } / \, parse-style
#: patterns { }, Gherkin outlines < > and tables |, quotes delimiting a parameter.
_UNSAFE = re.compile(r"[(){}\[\]/\\<>|\"`$^*+=~#@;:]")


@dataclass
class StepDef:
    """One step definition: a phrase bound to one page call (or, for ``arrive``, the taps
    that reach a page)."""

    keyword: str  # "Given" | "When" | "Then"
    text: str  # the pattern, with PARAM where the step takes a value
    page: str  # the PageDef it drives
    op: str  # "arrive", "stays" (still on the page after a tap on it) or a Call.op
    element: Optional[str] = None
    path: List[Call] = field(default_factory=list)  # arrive: the taps from the app's start
    sample: Optional[str] = None  # enter_long: the fixed value it types (a long run of one char)

    @property
    def has_param(self) -> bool:
        """Whether the step takes a (quoted string) value."""
        return PARAM in self.text


@dataclass
class GherkinStep:
    """One line of a scenario."""

    keyword: str  # "Given" | "When" | "Then" | "And"
    step: StepDef
    value: Optional[str] = None  # the concrete value, or "<column>" inside an outline

    @property
    def text(self) -> str:
        """The step as written in the feature file."""
        if not self.step.has_param:
            return self.step.text
        return self.step.text.replace(PARAM, f'"{self.value or ""}"')


@dataclass
class GherkinScenario:
    """A Scenario, or a Scenario Outline when ``examples`` is set."""

    title: str
    steps: List[GherkinStep]
    examples: Optional[Tuple[List[str], List[List[str]]]] = None  # (columns, rows)
    tags: List[str] = field(default_factory=list)  # e.g. "defect" — rendered as @defect


@dataclass
class Feature:
    """One feature file: the scenarios about one screen."""

    page: str
    title: str
    background: List[GherkinStep]
    scenarios: List[GherkinScenario]


@dataclass
class BddModel:
    """Everything a BDD renderer needs: the page objects, the features and the step catalog."""

    fm: FrameworkModel
    features: List[Feature]
    steps: List[StepDef]  # only steps some feature uses, grouped by page in page order

    def steps_for(self, page: str) -> List[StepDef]:
        """The step definitions that drive ``page``."""
        return [s for s in self.steps if s.page == page]


def _words(text: str) -> str:
    """Free text made safe for a step phrase (see ``_UNSAFE``), whitespace collapsed."""
    return " ".join(_UNSAFE.sub(" ", text or "").split())


def safe_value(value: Optional[str]) -> str:
    """A step's quoted value made safe for every target: no quote to end it early, no
    newline to split the step, no table/outline syntax."""
    return " ".join(re.sub(r"[\"\\|<>]", "'", value or "").split())


def _label(page: PageDef, key: str) -> str:
    """How a step names an element — its crawl label, else its key in words."""
    e = page.element(key)
    return _words(e.label) or key.replace("_", " ")


def _phrase(op: str, page: PageDef, key: Optional[str], sample: Optional[str] = None) -> Tuple[str, str]:
    """(keyword, phrase) for a page call."""
    title = _words(page.title) or page.name
    label = _label(page, key) if key else ""
    return {
        "arrive": ("Given", f"I am on the {title} screen"),
        "tap": ("When", f"I tap {label}"),
        "enter": ("When", f"I enter {PARAM} into {label}"),
        "enter_long": ("When", f"I enter {len(sample or '')} characters into {label}"),
        "is_displayed": ("Then", f"I see the {title} screen"),
        "stays": ("Then", f"I am still on the {title} screen"),
        "has": ("Then", f"I see {label}"),
        "lacks": ("Then", f"I do not see {label}"),
        "text_is": ("Then", f"{label} shows {PARAM}"),
        "is_enabled": ("Then", f"{label} is enabled"),
        "app_running": ("Then", "the app is still running"),
        "back": ("When", "I go back"),
    }[op]


def _arrival_paths(fm: FrameworkModel) -> Dict[str, List[Call]]:
    """Per page, the shortest run of navigating taps some scenario used to reach it from the
    app's start — a path known to work without input. The entry page is reached by none."""
    if not fm.pages:
        return {}
    entry = fm.pages[0].name
    paths: Dict[str, List[Call]] = {entry: []}
    for sc in fm.scenarios:
        current = entry
        taken: List[Call] = []
        for call in sc.calls:
            if call.op != "tap" or call.page != current or call.element is None:
                break
            target = fm.page(current).element(call.element).navigates_to
            if not target:
                break
            taken = [*taken, call]
            current = target
            if current not in paths or len(taken) < len(paths[current]):
                paths[current] = taken
    return paths


def _split(fm: FrameworkModel, sc: Scenario, paths: Dict[str, List[Call]]) -> Tuple[str, List[Call]]:
    """(the page the scenario starts on, the calls it makes there).

    The navigating taps that only *reach* the screen a scenario is about become ``Given I am
    on <screen>`` — unless reaching it IS the behaviour (all that follows is the arrival
    check), which stays a When/Then."""
    entry = fm.pages[0].name
    current, k = entry, 0
    for i, call in enumerate(sc.calls):
        if call.op != "tap" or call.page != current or call.element is None:
            break
        target = fm.page(current).element(call.element).navigates_to
        if not target:
            break
        current, k = target, i + 1
    if k == 0 or current not in paths or fm.page(current).identity is None:
        return entry, sc.calls
    rest = sc.calls[k:]
    if rest and rest[0].op == "is_displayed" and rest[0].page == current:
        rest = rest[1:]  # arriving already proves the screen is shown
    if not rest:
        return entry, sc.calls
    return current, rest


class _Catalog:
    """Builds step definitions on demand, one per (page, op, element), with phrases unique
    across the suite."""

    def __init__(self, fm: FrameworkModel, paths: Dict[str, List[Call]]):
        self.fm, self.paths = fm, paths
        self.defs: Dict[Tuple[str, str, Optional[str], Optional[str]], StepDef] = {}

    def get(self, page: str, op: str, element: Optional[str] = None, sample: Optional[str] = None) -> StepDef:
        """The step definition for a page call, created on first use."""
        key = (page, op, element, sample)
        if key not in self.defs:
            keyword, text = _phrase(op, self.fm.page(page), element, sample)
            self.defs[key] = StepDef(keyword, text, page, op, element, list(self.paths.get(page, [])), sample)
        return self.defs[key]

    def finish(self) -> List[StepDef]:
        """Disambiguate phrases shared by steps on different pages, then order by page."""
        by_text: Dict[str, List[StepDef]] = {}
        for d in self.defs.values():
            by_text.setdefault(d.text, []).append(d)
        for clash in (group for group in by_text.values() if len(group) > 1):
            for d in clash:
                page = self.fm.page(d.page)
                d.text = f"{d.text} on the {_words(page.title) or page.name} screen"
        seen: Set[str] = set()
        for d in self.defs.values():  # two same-titled pages: fall back to the class stem
            if d.text in seen:
                d.text = f"{d.text} {d.page}"
            seen.add(d.text)
        order = {p.name: i for i, p in enumerate(self.fm.pages)}
        clause = {"Given": 0, "When": 1, "Then": 2}
        return sorted(self.defs.values(), key=lambda d: (order[d.page], clause[d.keyword]))


def _lines(catalog: _Catalog, start: str, calls: List[Call], with_given: bool) -> List[GherkinStep]:
    """A scenario's steps, keywords folded to And where the clause repeats."""
    steps: List[GherkinStep] = []
    if with_given:
        steps.append(GherkinStep("Given", catalog.get(start, "arrive")))
        if len(calls) > 1 and calls[0].op == "is_displayed" and calls[0].page == start:
            calls = calls[1:]  # the Given already proved this screen is shown
    for i, call in enumerate(calls):
        op = call.op
        if op in ("app_running", "back"):  # not about any one screen: one definition, on the entry page
            d = catalog.get(catalog.fm.pages[0].name, op)
            steps.append(GherkinStep(d.keyword, d))
            continue
        if op == "is_displayed" and i and calls[i - 1].op == "tap" and calls[i - 1].page == call.page:
            op = "stays"  # the tap was meant to go nowhere (a rejected form)
        if op == "enter" and repeated(call.value):  # too-long input: say its length, not 300 x's
            d = catalog.get(call.page, "enter_long", call.element, sample=call.value)
            steps.append(GherkinStep(d.keyword, d))
            continue
        d = catalog.get(call.page, op, call.element)
        steps.append(GherkinStep(d.keyword, d, safe_value(call.value) if d.has_param else None))
    prev = None
    for s in steps:
        clause = s.step.keyword
        s.keyword = "And" if clause == prev else clause
        prev = clause
    return steps


def _title(sc: Scenario) -> str:
    """A scenario's title: its description's first sentence, as a phrase."""
    return _words(sc.title) or sc.name.replace("_", " ")


def _outlines(scenarios: List[GherkinScenario]) -> List[GherkinScenario]:
    """Merge scenarios that differ ONLY in the values they enter into one Scenario Outline —
    the data table then carries the variation. Anything else stays a plain Scenario."""
    groups: List[List[GherkinScenario]] = []
    by_shape: Dict[tuple, List[GherkinScenario]] = {}
    for sc in scenarios:
        shape = tuple((s.step.text, s.value if s.step.op != "enter" else None) for s in sc.steps)
        if any(s.step.op == "enter" for s in sc.steps) and shape in by_shape:
            by_shape[shape].append(sc)
            continue
        group = [sc]
        by_shape.setdefault(shape, group)
        groups.append(group)
    for group in (g for g in groups if len(g) > 1):
        sc = group[0]
        enters = [i for i, s in enumerate(sc.steps) if s.step.op == "enter"]
        columns: List[str] = []
        for i in enters:
            base = sc.steps[i].step.element or "value"
            name, n = base, 2
            while name in columns:
                name, n = f"{base}_{n}", n + 1
            columns.append(name)
        rows = [[v.steps[i].value or "" for i in enters] for v in group]
        sc.title = _merged_title([v.title for v in group])
        for i, col in zip(enters, columns):
            sc.steps[i].value = f"<{col}>"
        sc.examples = (columns, rows)
    return [g[0] for g in groups]


def _merged_title(titles: List[str]) -> str:
    """One title for scenarios merged into an Outline: the words they share, with the parts
    that differ joined by "or" — "Submitting the form with invalid data or empty fields is
    rejected"."""
    if len(set(titles)) == 1:
        return titles[0]
    words = [t.split() for t in titles]
    head = 0
    while all(len(w) > head for w in words) and len({w[head] for w in words}) == 1:
        head += 1
    tail = 0
    while all(len(w) > head + tail for w in words) and len({w[-1 - tail] for w in words}) == 1:
        tail += 1
    middles = []
    for w in words:
        middle = " ".join(w[head : len(w) - tail])
        if middle and middle not in middles:
            middles.append(middle)
    parts = [
        " ".join(words[0][:head]),
        " or ".join(middles),
        " ".join(words[0][len(words[0]) - tail :] if tail else []),
    ]
    return " ".join(p for p in parts if p)


def build_bdd_model(fm: FrameworkModel) -> BddModel:
    """The Page-Object framework model -> declarative features + a thin step catalog."""
    if not fm.pages:
        return BddModel(fm=fm, features=[], steps=[])
    paths = _arrival_paths(fm)
    catalog = _Catalog(fm, paths)
    by_group: Dict[str, List[Scenario]] = {}
    for sc in fm.scenarios:
        by_group.setdefault(sc.group, []).append(sc)

    features: List[Feature] = []
    for page in fm.pages:
        if page.name not in by_group:
            continue
        scenarios: List[GherkinScenario] = []
        titles: Set[str] = set()
        for sc in by_group[page.name]:
            start, calls = _split(fm, sc, paths)
            # "Given I am on <start>" needs something to prove it — the start page's identity.
            with_given = fm.page(start).identity is not None
            title = _title(sc)
            if title in titles:
                title = f"{title} ({sc.name.replace('_', ' ')})"
            titles.add(title)
            tags = ["defect"] if sc.defect else []
            scenarios.append(GherkinScenario(title, _lines(catalog, start, calls, with_given), tags=tags))
        scenarios = _outlines(scenarios)
        background: List[GherkinStep] = []
        firsts = {gs.steps[0].step.text if gs.steps else None for gs in scenarios}
        if (
            len(scenarios) > 1
            and len(firsts) == 1
            and all(gs.steps and gs.steps[0].keyword == "Given" for gs in scenarios)
        ):
            background = [scenarios[0].steps[0]]
            for gs in scenarios:
                gs.steps = gs.steps[1:]
                if gs.steps and gs.steps[0].keyword == "And":
                    gs.steps[0].keyword = gs.steps[0].step.keyword
        features.append(Feature(page.name, page.title, background, scenarios))
    return BddModel(fm=fm, features=features, steps=catalog.finish())


def render_feature(feature: Feature, app_package: str) -> str:
    """One ``.feature`` file — identical for every step-definition language."""
    out = [
        f"Feature: {_words(feature.title) or feature.page} screen",
        f"  What the {_words(feature.title) or feature.page} screen of {app_package} shows and does.",
        "  Auto-generated by Mobiscout. Regenerate rather than hand-edit.",
        "",
    ]
    if feature.background:
        out.append("  Background:")
        out += [f"    {s.keyword} {s.text}" for s in feature.background]
        out.append("")
    for sc in feature.scenarios:
        if sc.tags:
            out.append("  " + " ".join(f"@{t}" for t in sc.tags))
        out.append(f"  {'Scenario Outline' if sc.examples else 'Scenario'}: {sc.title}")
        out += [f"    {s.keyword} {s.text}" for s in sc.steps]
        if sc.examples:
            columns, rows = sc.examples
            out += ["", "    Examples:", "      | " + " | ".join(columns) + " |"]
            out += ["      | " + " | ".join(row) + " |" for row in rows]
        out.append("")
    return "\n".join(out)
