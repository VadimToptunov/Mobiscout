"""Crawl-coverage artifact — an honest map of what the crawl reached and what the
generated kit actually tests.

Answers the question a QA lead asks of any auto-generated suite: *what did it cover,
and what did it miss?* From the crawl result, the interaction graph, and the built test
model it computes, without any live device:

  - **Reach**: screens discovered, reachable from entry, unreachable (no modelled path),
    dead-ends (exploration stopped), and gated (reached only behind auth).
  - **Test coverage**: of the reachable screens and interactive elements, how many are
    exercised by at least one generated case.
  - **Targetability**: of those interactive elements, how many carry a resource-id or an
    accessibility label — i.e. an identity that survives a copy change or a translation,
    rather than a caption the kit had to locate by.
  - **Gaps**: reachable screens with no test, dead-ends, unreachable screens, and any
    error/loading/permission screens the crawl walked into.

It is deliberately conservative: an element counts as covered only when one of its
identity strings (resource-id / accessibility label / visible text) actually appears in a
generated case, so the numbers never over-claim.

    report = build_coverage(result, graph, model)
    (out / "coverage.md").write_text(report.to_markdown(package))
    (out / "coverage.json").write_text(report.to_json())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from framework.codegen.ir import TestModel
from framework.crawler.graph import InteractionGraph
from framework.crawler.models import CrawlElement, CrawlResult, CrawlScreen


def _used_locator_values(model: TestModel) -> set:
    """Every locator value (and fallback / description) the generated cases reference."""
    used: set = set()
    for case in model.cases:
        for step in case.steps:
            sel = step.selector
            if sel is None:
                continue
            used.add(sel.value.strip())
            if sel.description:
                used.add(sel.description.strip())
            for fb in sel.fallbacks:
                used.add(fb.value.strip())
    used.discard("")
    return used


def _element_identity(el: CrawlElement) -> List[str]:
    """The strings by which a generated locator could name this element."""
    return [v for v in (el.resource_id, el.content_desc, el.text) if v and v.strip()]


def _element_covered(el: CrawlElement, used: set) -> bool:
    """True if any identity string of ``el`` appears among the used locator values."""
    return any(v.strip() in used for v in _element_identity(el))


def _element_targetable(el: CrawlElement) -> bool:
    """True if the element carries an identity a locator can key on that is not content.

    Visible text is deliberately excluded here, unlike in :func:`_element_identity`: a
    caption is content, so it moves with a copy change or a translation. Only a resource-id
    or an accessibility label survives that, and the gap between the two counts is exactly
    what the crawl could not target stably.
    """
    return bool((el.resource_id or "").strip() or (el.content_desc or "").strip())


@dataclass
class ScreenCoverage:
    """Reach and test-coverage facts for one crawled screen."""

    screen_id: int  # graph node id, or -1 if the screen isn't in the graph
    fingerprint: str
    depth: int  # BFS distance from entry; -1 = unreachable
    elements: int
    interactive: int
    covered_elements: int
    targetable: int = 0  # interactive elements carrying a resource-id or accessibility label
    is_entry: bool = False
    dead_end: bool = False
    gated: bool = False
    edge_case: Optional[str] = None  # error/loading/permission screen kind, if flagged

    @property
    def reachable(self) -> bool:
        """True if the screen has a modelled path from the entry (or is the entry)."""
        return self.depth >= 0 or self.is_entry

    @property
    def tested(self) -> bool:
        """True if at least one interactive element here is exercised by a generated case."""
        return self.covered_elements > 0

    def to_dict(self) -> Dict[str, object]:
        """Serialize this screen's coverage facts to a JSON-safe dict."""
        return {
            "screen_id": self.screen_id,
            "fingerprint": self.fingerprint,
            "depth": self.depth,
            "elements": self.elements,
            "interactive": self.interactive,
            "covered_elements": self.covered_elements,
            "targetable": self.targetable,
            "reachable": self.reachable,
            "tested": self.tested,
            "is_entry": self.is_entry,
            "dead_end": self.dead_end,
            "gated": self.gated,
            "edge_case": self.edge_case,
        }


# Where the Compose team documents the switch that turns testTag into a resource-id.
COMPOSE_TESTTAG_DOCS = "https://developer.android.com/develop/ui/compose/testing#uiautomator-interop"

# Guidance shown for a Compose app. Compose emits every tappable control as an anonymous
# `android.view.View` whose label sits on a child, so the crawler has to infer a locator
# from the visible caption. That works (it is what makes these apps testable at all) but a
# caption is content: it moves with copy changes and translations. One app-side switch
# turns every testTag into a real resource-id, which is stable — so say so, once, where the
# user actually reads the numbers.
_COMPOSE_ADVICE = f"""
## Locators on this app

This app is built with **Jetpack Compose**, which exposes tappable controls as anonymous
views — their visible caption is the only thing left to locate them by. The generated
tests therefore locate by text / content-description, which works but breaks on a copy
change or a translation.

For stable locators, give the controls a `Modifier.testTag("...")` and switch on
`testTagsAsResourceId = true` — **in the debug/test build variant only**, not in release:
it publishes your internal tags as resource-ids, which the app has no reason to ship to
users. Crawl that build and each tag arrives as a real resource-id the next crawl prefers
automatically. See {COMPOSE_TESTTAG_DOCS}.

"""


# Apple's modifier/property that gives a control a stable, non-visible identifier.
IOS_A11Y_DOCS = "https://developer.apple.com/documentation/swiftui/view/accessibilityidentifier(_:)"

# The iOS counterpart of the Compose note. XCUITest reports a control's accessibility
# IDENTIFIER as `name` — but when the app sets no identifier it echoes the visible label
# there instead, so "has a name" is not the same as "has a stable id". When most controls
# only echo their label, every generated locator is really content, and the suite breaks on
# the next copy change or localisation.
_IOS_ADVICE = f"""
## Locators on this app

Most controls here expose no **accessibility identifier** — XCUITest echoes their visible
label instead, so the generated tests locate by that label. It works, but it breaks on a
copy change or a translation.

For stable locators, give the controls an identifier: `.accessibilityIdentifier("...")` in
SwiftUI, or `view.accessibilityIdentifier = "..."` in UIKit. It is invisible to users and
to VoiceOver (it is not the spoken label), and the next crawl will prefer it automatically.
See {IOS_A11Y_DOCS}.

"""

# Below this share of interactive controls carrying a real identifier, the iOS advice is
# worth showing: a handful of identified controls in an otherwise label-located app still
# leaves the suite content-dependent.
_IOS_ID_THRESHOLD = 0.5


def _ios_identifier_ratio(result: "CrawlResult") -> float:
    """Share of interactive controls that carry a real accessibility identifier.

    A control whose `name` merely repeats its `label` has no identifier of its own —
    XCUITest just echoed the label — so it does not count.
    """
    interactive = [e for screen in result.screens.values() for e in screen.interactive()]
    if not interactive:
        return 1.0  # nothing to advise about
    identified = sum(
        1 for e in interactive if e.resource_id and e.resource_id.strip() != (e.content_desc or "").strip()
    )
    return identified / len(interactive)


# Same idea as the iOS threshold: below this share of interactive controls carrying a
# resource-id or accessibility label, the kit is locating by caption and the advice earns
# its place. An app that already tags its controls should not be lectured about it.
_TARGETABLE_THRESHOLD = 0.5


def targetable_ratio(result: "CrawlResult") -> float:
    """Share of interactive controls the crawl could target by something other than text."""
    interactive = [e for screen in result.screens.values() for e in screen.interactive()]
    if not interactive:
        return 0.0  # nothing measured yet — a fresh Compose app still deserves the guidance
    return sum(1 for e in interactive if _element_targetable(e)) / len(interactive)


def compose_locator_advice(toolkit: str, result: "CrawlResult") -> str:
    """The Compose locator guidance, or "" for another toolkit or an already-tagged app."""
    if (toolkit or "").lower() != "compose":
        return ""
    return _COMPOSE_ADVICE if targetable_ratio(result) < _TARGETABLE_THRESHOLD else ""


def locator_advice(toolkit: str, platform: str, result: "CrawlResult") -> str:
    """Toolkit-specific guidance on making the generated locators stable, or "".

    Both cases say the same thing for their platform: the crawl had nothing but visible
    text to locate by, which is content — here is the one app-side change that fixes it.
    """
    if (platform or "").lower() == "ios":
        return _IOS_ADVICE if _ios_identifier_ratio(result) < _IOS_ID_THRESHOLD else ""
    return compose_locator_advice(toolkit, result)


@dataclass
class CoverageReport:
    """Reach + test coverage for a whole crawl, with per-screen detail and gap views."""

    screens: List[ScreenCoverage] = field(default_factory=list)
    cases: int = 0

    # ---- headline aggregates ------------------------------------------------
    @property
    def screens_total(self) -> int:
        """Every screen discovered by the crawl (reachable or not)."""
        return len(self.screens)

    @property
    def screens_reachable(self) -> int:
        """Screens with a modelled path from the entry."""
        return sum(1 for s in self.screens if s.reachable)

    @property
    def screens_tested(self) -> int:
        """Reachable screens exercised by at least one generated case."""
        return sum(1 for s in self.screens if s.reachable and s.tested)

    @property
    def screens_untested(self) -> List[ScreenCoverage]:
        """Reachable screens no generated case touches — the coverage gaps."""
        return [s for s in self.screens if s.reachable and not s.tested]

    @property
    def unreachable(self) -> List[ScreenCoverage]:
        """Screens discovered but with no modelled path from the entry."""
        return [s for s in self.screens if not s.reachable]

    @property
    def dead_ends(self) -> List[ScreenCoverage]:
        """Screens with no outgoing transition — where exploration stopped."""
        return [s for s in self.screens if s.dead_end]

    @property
    def gated(self) -> List[ScreenCoverage]:
        """Screens reached only after passing an auth gate."""
        return [s for s in self.screens if s.gated]

    @property
    def edge_cases(self) -> List[ScreenCoverage]:
        """Error/loading/permission screens the crawl walked into."""
        return [s for s in self.screens if s.edge_case]

    @property
    def elements_total(self) -> int:
        """Total interactive elements discovered across all screens."""
        return sum(s.interactive for s in self.screens)

    @property
    def elements_covered(self) -> int:
        """Interactive elements exercised by a generated case."""
        return sum(s.covered_elements for s in self.screens)

    def screen_coverage_pct(self) -> int:
        """Percent of reachable screens that at least one case tests (0 if none)."""
        base = self.screens_reachable
        return round(100 * self.screens_tested / base) if base else 0

    def element_coverage_pct(self) -> int:
        """Percent of interactive elements a generated case covers (0 if none)."""
        base = self.elements_total
        return round(100 * self.elements_covered / base) if base else 0

    @property
    def elements_targetable(self) -> int:
        """Interactive elements carrying a resource-id or accessibility label."""
        return sum(s.targetable for s in self.screens)

    def targetability_pct(self) -> int:
        """Percent of interactive elements locatable by something other than visible text."""
        base = self.elements_total
        return round(100 * self.elements_targetable / base) if base else 0

    def to_dict(self) -> Dict[str, object]:
        """Serialize the whole report (headline aggregates + per-screen list) to a dict."""
        return {
            "cases": self.cases,
            "screens_total": self.screens_total,
            "screens_reachable": self.screens_reachable,
            "screens_tested": self.screens_tested,
            "screen_coverage_pct": self.screen_coverage_pct(),
            "elements_interactive": self.elements_total,
            "elements_covered": self.elements_covered,
            "element_coverage_pct": self.element_coverage_pct(),
            "elements_targetable": self.elements_targetable,
            "targetability_pct": self.targetability_pct(),
            "unreachable": len(self.unreachable),
            "dead_ends": len(self.dead_ends),
            "gated": len(self.gated),
            "screens": [s.to_dict() for s in self.screens],
        }

    def to_json(self) -> str:
        """The report as pretty-printed JSON (CI-friendly, e.g. gate on coverage %)."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    def to_markdown(self, app_package: str = "", advice: str = "") -> str:
        """The report as human-readable Markdown: headline, gaps, and a per-screen table."""
        head = f"# Crawl coverage{f' — {app_package}' if app_package else ''}\n\n"
        summary = (
            f"- Screens: **{self.screens_tested}/{self.screens_reachable}** reachable screens tested "
            f"(**{self.screen_coverage_pct()}%**){_of_total(self.screens_total, self.screens_reachable)}\n"
            f"- Interactive elements: **{self.elements_covered}/{self.elements_total}** covered "
            f"(**{self.element_coverage_pct()}%**)\n"
            f"- Targetable elements: **{self.elements_targetable}/{self.elements_total}** carry a "
            f"resource-id or accessibility label (**{self.targetability_pct()}%**); the rest can "
            f"only be located by their visible text\n"
            f"- Generated cases: **{self.cases}**\n"
        )
        gaps = self._gaps_markdown()
        table = self._table_markdown()
        return head + summary + advice + gaps + table

    # ---- markdown sections --------------------------------------------------
    def _gaps_markdown(self) -> str:
        """Render the gap sections (untested / unreachable / gated / dead-end / edge-case)."""
        out = ""
        if self.screens_untested:
            out += (
                f"\n## Reachable but untested ({len(self.screens_untested)})\n\n"
                "Screens the crawl reached but no generated case exercises "
                "(often no locatable interactive element):\n\n"
                + "".join(
                    f"- screen #{s.screen_id} (depth {s.depth}, {s.interactive} interactive)\n"
                    for s in self.screens_untested
                )
            )
        if self.unreachable:
            out += (
                f"\n## Unreachable ({len(self.unreachable)})\n\n"
                "Discovered but with no modelled path from the entry — point the crawl at them "
                "or add a waypoint:\n\n"
                + "".join(f"- `{s.fingerprint[:16]}` ({s.interactive} interactive)\n" for s in self.unreachable)
            )
        if self.gated:
            out += (
                f"\n## Behind auth ({len(self.gated)})\n\n"
                "Reached only after passing a gate (login/OTP); generated tests prepend the auth prefix:\n\n"
                + "".join(f"- screen #{s.screen_id} (depth {s.depth})\n" for s in self.gated)
            )
        if self.dead_ends:
            out += (
                f"\n## Dead-ends ({len(self.dead_ends)})\n\n"
                "Exploration stopped here (no outgoing transition) — a deeper crawl may find more:\n\n"
                + "".join(f"- screen #{s.screen_id} (depth {s.depth})\n" for s in self.dead_ends)
            )
        if self.edge_cases:
            out += f"\n## Edge-case screens reached ({len(self.edge_cases)})\n\n" + "".join(
                f"- screen #{s.screen_id}: {s.edge_case}\n" for s in self.edge_cases
            )
        return out

    def _table_markdown(self) -> str:
        """Render the per-screen table (depth, interactive/covered counts, tested, notes)."""
        rows = [
            "\n## All screens\n",
            "| Screen | Depth | Interactive | Targetable | Covered | Tested | Notes |",
            "|---:|---:|---:|---:|---:|:---:|---|",
        ]
        for s in sorted(self.screens, key=lambda x: (x.screen_id if x.screen_id > 0 else 1 << 30)):
            notes = ", ".join(
                n
                for n in (
                    "entry" if s.is_entry else "",
                    "gated" if s.gated else "",
                    "dead-end" if s.dead_end else "",
                    "unreachable" if not s.reachable else "",
                    s.edge_case or "",
                )
                if n
            )
            sid = f"#{s.screen_id}" if s.screen_id > 0 else f"`{s.fingerprint[:8]}`"
            rows.append(
                f"| {sid} | {s.depth} | {s.interactive} | {s.targetable} | {s.covered_elements} | "
                f"{'✅' if s.tested else '—'} | {notes} |"
            )
        return "\n".join(rows) + "\n"


def _of_total(total: int, reachable: int) -> str:
    """A trailing clause noting screens discovered but unreachable, or '' when none."""
    extra = total - reachable
    return f"; {extra} more discovered but unreachable" if extra > 0 else ""


def build_coverage(result: CrawlResult, graph: InteractionGraph, model: TestModel) -> CoverageReport:
    """Compute a :class:`CoverageReport` from a crawl, its graph, and the built test model."""
    used = _used_locator_values(model)
    by_fp = {n.fingerprint: n for n in graph.nodes}
    dead_end_ids = set(graph.dead_ends())
    gated_fps = getattr(result, "gated", None) or set()
    # Count only the elements the app owns, the same filter codegen applies (_owned). A
    # dump routinely carries clickable nodes from system UI, a permission dialog or the
    # IME keyboard (dozens of key nodes on any screen captured with the keyboard up); no
    # generated case can ever target those, so counting them inflates the denominator and
    # under-reports element coverage — a number teams gate CI on.
    owned_packages = ("", model.app_package)

    screens: List[ScreenCoverage] = []
    for fp, screen in result.screens.items():
        node = by_fp.get(fp)
        interactive: List[CrawlElement] = (
            [e for e in screen.interactive() if e.package in owned_packages] if isinstance(screen, CrawlScreen) else []
        )
        covered = sum(1 for el in interactive if _element_covered(el, used))
        targetable = sum(1 for el in interactive if _element_targetable(el))
        screens.append(
            ScreenCoverage(
                screen_id=node.id if node else -1,
                fingerprint=fp,
                depth=node.depth if node else -1,
                elements=len(screen.elements),
                interactive=len(interactive),
                covered_elements=covered,
                targetable=targetable,
                is_entry=bool(node and node.is_entry),
                dead_end=bool(node and node.id in dead_end_ids),
                gated=fp in gated_fps,
                edge_case=node.edge_case if node else None,
            )
        )
    return CoverageReport(screens=screens, cases=len(model.cases))
