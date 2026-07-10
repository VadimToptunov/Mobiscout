"""
Structural invariants — what's wrong with the app's navigation, from its graph.

The interaction graph already knows the shape of the app; this reads structural
problems off it that a tester should see: screens the user can never reach,
screens that trap the user (no way forward), and screens from which there's no
way back to the start. These are real usability/testability findings, derived
with no extra crawling.

    for v in check_invariants(graph):
        print(v.severity, v.message)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import List

from framework.crawler.graph import InteractionGraph


@dataclass
class Invariant:
    """A violated structural expectation about the app's navigation."""

    name: str
    severity: str  # "error" | "warning"
    screens: List[int]
    message: str


def _can_reach(graph: InteractionGraph, src: int, dst: int) -> bool:
    """Is ``dst`` reachable from ``src`` following directed transitions?"""
    if src == dst:
        return True
    adj = graph._adj()
    seen = {src}
    q = deque([src])
    while q:
        cur = q.popleft()
        for edge in adj.get(cur, []):
            if edge.dst == dst:
                return True
            if edge.dst not in seen:
                seen.add(edge.dst)
                q.append(edge.dst)
    return False


def check_invariants(graph: InteractionGraph) -> List[Invariant]:
    """Structural problems in the crawled navigation graph."""
    out: List[Invariant] = []
    if not graph.nodes or graph.entry is None:
        return out

    unreachable = graph.unreachable()
    if unreachable:
        out.append(
            Invariant(
                "unreachable_screens",
                "error",
                unreachable,
                f"{len(unreachable)} screen(s) can't be reached from the entry: {_fmt(unreachable)}.",
            )
        )

    dead_ends = graph.dead_ends()
    if dead_ends:
        out.append(
            Invariant(
                "dead_ends",
                "warning",
                dead_ends,
                f"{len(dead_ends)} screen(s) trap the user (no way forward): {_fmt(dead_ends)}.",
            )
        )

    # Screens from which the entry (login/home) can't be reached again.
    no_return = [
        n.id for n in graph.nodes if n.depth >= 0 and not n.is_entry and not _can_reach(graph, n.id, graph.entry)
    ]
    if no_return:
        out.append(
            Invariant(
                "no_return_path",
                "warning",
                no_return,
                f"{len(no_return)} screen(s) have no path back to the entry: {_fmt(no_return)}.",
            )
        )

    return out


def _fmt(ids: List[int]) -> str:
    return ", ".join(f"screen {i}" for i in ids)


def invariants_markdown(graph: InteractionGraph) -> str:
    """A tester-facing report of structural findings (empty-clean if none)."""
    violations = check_invariants(graph)
    out = ["# Structural invariants", ""]
    if not violations:
        out.append("No structural issues: every screen is reachable, none trap the user, all can return to the entry.")
        return "\n".join(out) + "\n"
    icon = {"error": "🔴", "warning": "🟡"}
    for v in violations:
        out.append(f"- {icon.get(v.severity, '•')} **{v.name}** — {v.message}")
    return "\n".join(out) + "\n"
