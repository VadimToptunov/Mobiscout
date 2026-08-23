"""Crawl-coverage artifact — an honest map of what the crawl reached and what the
generated kit actually tests.

Answers the question a QA lead asks of any auto-generated suite: *what did it cover,
and what did it miss?* From the crawl result, the interaction graph, and the built test
model it computes, without any live device:

  - **Reach**: screens discovered, reachable from entry, unreachable (no modelled path),
    dead-ends (exploration stopped), and gated (reached only behind auth).
  - **Test coverage**: of the reachable screens and interactive elements, how many are
    exercised by at least one generated case.
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
    return any(v.strip() in used for v in _element_identity(el))


@dataclass
class ScreenCoverage:
    screen_id: int  # graph node id, or -1 if the screen isn't in the graph
    fingerprint: str
    depth: int  # BFS distance from entry; -1 = unreachable
    elements: int
    interactive: int
    covered_elements: int
    is_entry: bool = False
    dead_end: bool = False
    gated: bool = False
    edge_case: Optional[str] = None  # error/loading/permission screen kind, if flagged

    @property
    def reachable(self) -> bool:
        return self.depth >= 0 or self.is_entry

    @property
    def tested(self) -> bool:
        return self.covered_elements > 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "screen_id": self.screen_id,
            "fingerprint": self.fingerprint,
            "depth": self.depth,
            "elements": self.elements,
            "interactive": self.interactive,
            "covered_elements": self.covered_elements,
            "reachable": self.reachable,
            "tested": self.tested,
            "is_entry": self.is_entry,
            "dead_end": self.dead_end,
            "gated": self.gated,
            "edge_case": self.edge_case,
        }


@dataclass
class CoverageReport:
    screens: List[ScreenCoverage] = field(default_factory=list)
    cases: int = 0

    # ---- headline aggregates ------------------------------------------------
    @property
    def screens_total(self) -> int:
        return len(self.screens)

    @property
    def screens_reachable(self) -> int:
        return sum(1 for s in self.screens if s.reachable)

    @property
    def screens_tested(self) -> int:
        return sum(1 for s in self.screens if s.reachable and s.tested)

    @property
    def screens_untested(self) -> List[ScreenCoverage]:
        return [s for s in self.screens if s.reachable and not s.tested]

    @property
    def unreachable(self) -> List[ScreenCoverage]:
        return [s for s in self.screens if not s.reachable]

    @property
    def dead_ends(self) -> List[ScreenCoverage]:
        return [s for s in self.screens if s.dead_end]

    @property
    def gated(self) -> List[ScreenCoverage]:
        return [s for s in self.screens if s.gated]

    @property
    def edge_cases(self) -> List[ScreenCoverage]:
        return [s for s in self.screens if s.edge_case]

    @property
    def elements_total(self) -> int:
        return sum(s.interactive for s in self.screens)

    @property
    def elements_covered(self) -> int:
        return sum(s.covered_elements for s in self.screens)

    def screen_coverage_pct(self) -> int:
        base = self.screens_reachable
        return round(100 * self.screens_tested / base) if base else 0

    def element_coverage_pct(self) -> int:
        base = self.elements_total
        return round(100 * self.elements_covered / base) if base else 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "cases": self.cases,
            "screens_total": self.screens_total,
            "screens_reachable": self.screens_reachable,
            "screens_tested": self.screens_tested,
            "screen_coverage_pct": self.screen_coverage_pct(),
            "elements_interactive": self.elements_total,
            "elements_covered": self.elements_covered,
            "element_coverage_pct": self.element_coverage_pct(),
            "unreachable": len(self.unreachable),
            "dead_ends": len(self.dead_ends),
            "gated": len(self.gated),
            "screens": [s.to_dict() for s in self.screens],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    def to_markdown(self, app_package: str = "") -> str:
        head = f"# Crawl coverage{f' — {app_package}' if app_package else ''}\n\n"
        summary = (
            f"- Screens: **{self.screens_tested}/{self.screens_reachable}** reachable screens tested "
            f"(**{self.screen_coverage_pct()}%**){_of_total(self.screens_total, self.screens_reachable)}\n"
            f"- Interactive elements: **{self.elements_covered}/{self.elements_total}** covered "
            f"(**{self.element_coverage_pct()}%**)\n"
            f"- Generated cases: **{self.cases}**\n"
        )
        gaps = self._gaps_markdown()
        table = self._table_markdown()
        return head + summary + gaps + table

    # ---- markdown sections --------------------------------------------------
    def _gaps_markdown(self) -> str:
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
        rows = [
            "\n## All screens\n",
            "| Screen | Depth | Interactive | Covered | Tested | Notes |",
            "|---:|---:|---:|---:|:---:|---|",
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
                f"| {sid} | {s.depth} | {s.interactive} | {s.covered_elements} | "
                f"{'✅' if s.tested else '—'} | {notes} |"
            )
        return "\n".join(rows) + "\n"


def _of_total(total: int, reachable: int) -> str:
    extra = total - reachable
    return f"; {extra} more discovered but unreachable" if extra > 0 else ""


def build_coverage(result: CrawlResult, graph: InteractionGraph, model: TestModel) -> CoverageReport:
    """Compute a :class:`CoverageReport` from a crawl, its graph, and the built test model."""
    used = _used_locator_values(model)
    by_fp = {n.fingerprint: n for n in graph.nodes}
    dead_end_ids = set(graph.dead_ends())
    gated_fps = getattr(result, "gated", None) or set()

    screens: List[ScreenCoverage] = []
    for fp, screen in result.screens.items():
        node = by_fp.get(fp)
        interactive: List[CrawlElement] = screen.interactive() if isinstance(screen, CrawlScreen) else []
        covered = sum(1 for el in interactive if _element_covered(el, used))
        screens.append(
            ScreenCoverage(
                screen_id=node.id if node else -1,
                fingerprint=fp,
                depth=node.depth if node else -1,
                elements=len(screen.elements),
                interactive=len(interactive),
                covered_elements=covered,
                is_entry=bool(node and node.is_entry),
                dead_end=bool(node and node.id in dead_end_ids),
                gated=fp in gated_fps,
                edge_case=node.edge_case if node else None,
            )
        )
    return CoverageReport(screens=screens, cases=len(model.cases))
