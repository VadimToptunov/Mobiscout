"""
Interaction graph — the app's navigation model, as deep as the crawl allows.

A crawl yields screens and the transitions between them; this turns that into a
first-class directed graph and mines it:

* Nodes are screens, each carrying platform/toolkit, element count and a
  semantic-type histogram (buttons/inputs/… from the ML+heuristic classifier).
* Edges are transitions, each labelled with the action, the tapped element, its
  semantic type and the recommended locator — so an edge is a runnable step.

On top of the structure it computes reachability and BFS depth from the entry
screen, dead-ends, unreachable screens, cycles, hub screens, shortest paths from
the entry to every screen, and a set of paths that together cover every reachable
edge (the seed for multi-step, model-based test generation).

Exports to Mermaid (renders on GitHub / in a README), Graphviz DOT, and JSON.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from framework.codegen.ir import ActionType, AssertionType, Step, TestCase
from framework.crawler.app_crawler import CrawlResult, CrawlScreen
from framework.crawler.classify import classify
from framework.crawler.to_codegen import _owned, selector_for


@dataclass
class GraphNode:
    id: int  # 1-based, in crawl-discovery order
    fingerprint: str
    platform: str
    toolkit: str
    element_count: int
    type_histogram: Dict[str, int]
    is_entry: bool = False
    depth: int = -1  # BFS distance from entry; -1 = unreachable

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "platform": self.platform,
            "toolkit": self.toolkit,
            "element_count": self.element_count,
            "type_histogram": self.type_histogram,
            "is_entry": self.is_entry,
            "depth": self.depth,
        }


@dataclass
class GraphEdge:
    src: int
    dst: int
    action: str  # tap | type | ...
    label: str  # tapped element label
    element_type: str  # semantic type of the tapped element
    locator: str  # recommended locator "strategy=value"

    def to_dict(self) -> Dict:
        return {
            "src": self.src,
            "dst": self.dst,
            "action": self.action,
            "label": self.label,
            "element_type": self.element_type,
            "locator": self.locator,
        }


@dataclass
class InteractionGraph:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    entry: Optional[int] = None

    # ---- adjacency helpers -------------------------------------------------
    def _adj(self) -> Dict[int, List[GraphEdge]]:
        adj: Dict[int, List[GraphEdge]] = defaultdict(list)
        for e in self.edges:
            adj[e.src].append(e)
        return adj

    def _node(self, node_id: int) -> Optional[GraphNode]:
        return next((n for n in self.nodes if n.id == node_id), None)

    # ---- analysis ----------------------------------------------------------
    def unreachable(self) -> List[int]:
        return [n.id for n in self.nodes if n.depth < 0 and not n.is_entry]

    def dead_ends(self) -> List[int]:
        """Reachable screens with no outgoing transition (a tester may be stuck)."""
        outs = {e.src for e in self.edges}
        return [n.id for n in self.nodes if n.id not in outs and n.depth >= 0]

    def hubs(self, k: int = 3) -> List[Tuple[int, int]]:
        """Screens with the highest total degree (in+out) — navigation hubs."""
        deg: Counter = Counter()
        for e in self.edges:
            deg[e.src] += 1
            deg[e.dst] += 1
        return deg.most_common(k)

    def cycles(self) -> List[List[int]]:
        """Simple cycles via DFS back-edges (deduplicated by rotation)."""
        adj = self._adj()
        found: List[List[int]] = []
        seen = set()

        def dfs(node: int, stack: List[int], onstack: set) -> None:
            for e in adj.get(node, []):
                if e.dst in onstack:
                    cyc = stack[stack.index(e.dst) :]
                    key = frozenset(cyc)
                    if key not in seen:
                        seen.add(key)
                        found.append(cyc + [e.dst])
                elif e.dst not in visited:
                    visited.add(e.dst)
                    dfs(e.dst, stack + [e.dst], onstack | {e.dst})

        visited: set = set()
        for n in self.nodes:
            if n.id not in visited:
                visited.add(n.id)
                dfs(n.id, [n.id], {n.id})
        return found

    def shortest_paths_from_entry(self) -> Dict[int, List[int]]:
        """BFS shortest path (as node ids) from the entry to every reachable node."""
        if self.entry is None:
            return {}
        adj = self._adj()
        parent: Dict[int, Optional[int]] = {self.entry: None}
        q = deque([self.entry])
        while q:
            cur = q.popleft()
            for e in adj.get(cur, []):
                if e.dst not in parent:
                    parent[e.dst] = cur
                    q.append(e.dst)
        paths: Dict[int, List[int]] = {}
        for node in parent:
            path, cur2 = [], node
            while cur2 is not None:
                path.append(cur2)
                cur2 = parent[cur2]
            paths[node] = list(reversed(path))
        return paths

    def edge_coverage_paths(self) -> List[List[GraphEdge]]:
        """A set of entry-rooted walks that together cover every reachable edge —
        the seed for multi-step test generation (edge coverage)."""
        if self.entry is None:
            return []
        sp = self.shortest_paths_from_entry()
        adj = self._adj()
        covered: set = set()
        walks: List[List[GraphEdge]] = []
        for e in self.edges:
            if e.src not in sp or id(e) in covered:
                continue
            # walk = shortest path to e.src, then take e.
            prefix_nodes = sp[e.src]
            walk: List[GraphEdge] = []
            for a, b in zip(prefix_nodes, prefix_nodes[1:]):
                step = next((x for x in adj.get(a, []) if x.dst == b), None)
                if step:
                    walk.append(step)
            walk.append(e)
            for x in walk:
                covered.add(id(x))
            walks.append(walk)
        return walks

    def metrics(self) -> Dict:
        depths = [n.depth for n in self.nodes if n.depth >= 0]
        return {
            "screens": len(self.nodes),
            "transitions": len(self.edges),
            "max_depth": max(depths) if depths else 0,
            "unreachable": len(self.unreachable()),
            "dead_ends": len(self.dead_ends()),
            "cycles": len(self.cycles()),
        }

    def to_dict(self) -> Dict:
        return {
            "entry": self.entry,
            "metrics": self.metrics(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "dead_ends": self.dead_ends(),
            "unreachable": self.unreachable(),
            "hubs": self.hubs(),
        }


def build_graph(result: CrawlResult, app_package: str = "") -> InteractionGraph:
    """Build the interaction graph from a crawl, with typed, locatable edges."""
    fps = list(result.screens)
    id_of = {fp: i + 1 for i, fp in enumerate(fps)}

    nodes: List[GraphNode] = []
    for fp, screen in result.screens.items():
        owned = _owned(screen, app_package)
        hist: Counter = Counter(classify(e)[0] for e in owned)
        nodes.append(
            GraphNode(
                id=id_of[fp],
                fingerprint=fp,
                platform=screen.platform,
                toolkit=screen.toolkit,
                element_count=len(owned),
                type_histogram=dict(hist),
                is_entry=(fp == fps[0]) if fps else False,
            )
        )

    edges: List[GraphEdge] = []
    seen = set()
    for from_fp, element, to_fp in result.transitions:
        if from_fp not in id_of or to_fp not in id_of:
            continue
        src, dst = id_of[from_fp], id_of[to_fp]
        from_screen: CrawlScreen = result.screens[from_fp]
        sel = selector_for(element, _owned(from_screen, app_package), from_screen.platform)
        locator = f"{sel.strategy.value}={sel.value}" if sel else ""
        etype = classify(element)[0]
        key = (src, dst, element.label, etype)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            GraphEdge(
                src=src,
                dst=dst,
                action="tap",
                label=element.label or element.class_name,
                element_type=etype,
                locator=locator,
            )
        )

    graph = InteractionGraph(nodes=nodes, edges=edges, entry=id_of[fps[0]] if fps else None)
    _annotate_depth(graph)
    return graph


def _sample_value(element) -> str:
    """A realistic sample for a form field, inferred from its label/id/class."""
    hint = f"{element.text} {element.content_desc} {element.resource_id} {element.class_name}".lower()
    if "email" in hint or "e-mail" in hint:
        return "test@example.com"
    if "secure" in hint or any(k in hint for k in ("password", "passwd", "pwd", "pass")):
        return "Password123!"
    if any(k in hint for k in ("phone", "tel", "mobile")):
        return "1234567890"
    if "search" in hint or "query" in hint:
        return "test"
    if "name" in hint:
        return "Test User"
    return "Test"


def _form_steps(screen: CrawlScreen, app_package: str) -> List[Step]:
    """Type-aware interactions on one screen: fill inputs with sample data and
    toggle checkboxes/switches — so a path exercises forms, not just navigation."""
    steps: List[Step] = []
    owned = _owned(screen, app_package)
    seen = set()
    for e in owned:
        etype = classify(e)[0]
        if etype not in ("input", "checkbox", "switch"):
            continue
        sel = selector_for(e, owned, screen.platform)
        if sel is None or sel.value in seen:
            continue
        seen.add(sel.value)
        if etype == "input":
            steps.append(
                Step(
                    ActionType.TYPE, selector=sel, text=_sample_value(e), description=f"Type into {e.label or 'input'}"
                )
            )
        else:  # checkbox / switch -> toggle
            steps.append(Step(ActionType.TAP, selector=sel, description=f"Toggle {e.label or etype}"))
    return steps


def multi_step_cases(result: CrawlResult, app_package: str = "", max_cases: int = 12) -> List[TestCase]:
    """Model-based test cases: walk real paths through the interaction graph.

    Beyond navigating (login -> catalog -> cart -> pay), each screen along the way
    has its form filled — inputs get sample data, checkboxes/switches get toggled —
    so the paths exercise forms too. Paths are prioritised deepest/most-critical
    first, then capped, so the most valuable ones survive max_cases.
    """
    graph = build_graph(result, app_package)
    fps = list(result.screens)
    fp_of = {i + 1: fp for i, fp in enumerate(fps)}
    degree = {n.id: 0 for n in graph.nodes}
    for e in graph.edges:
        degree[e.src] = degree.get(e.src, 0) + 1
        degree[e.dst] = degree.get(e.dst, 0) + 1

    by_pair: Dict[Tuple[str, str], List] = defaultdict(list)
    for from_fp, element, to_fp in result.transitions:
        by_pair[(from_fp, to_fp)].append(element)

    def _landmark(screen: CrawlScreen):
        owned = _owned(screen, app_package)
        return next((s for s in (selector_for(e, owned, screen.platform) for e in owned) if s), None)

    # Keep only maximal walks (drop those that are a strict prefix of a longer one).
    raw_paths = [tuple([w[0].src] + [e.dst for e in w]) for w in graph.edge_coverage_paths() if len(w) >= 2]
    maximal = {p for p in raw_paths if not any(other != p and other[: len(p)] == p for other in raw_paths)}

    scored: List[Tuple[tuple, TestCase]] = []
    seen_paths = set()
    for walk in graph.edge_coverage_paths():
        if len(walk) < 2:
            continue
        node_path = tuple([walk[0].src] + [e.dst for e in walk])
        if node_path in seen_paths or node_path not in maximal:
            continue

        steps: List[Step] = [Step(ActionType.LAUNCH, description="Open app")]
        form_steps = 0
        taps: List[str] = []
        ok = True
        for edge in walk:
            from_fp, to_fp = fp_of[edge.src], fp_of[edge.dst]
            candidates = by_pair.get((from_fp, to_fp), [])
            element = next(
                (e for e in candidates if (e.label or e.class_name) == edge.label),
                candidates[0] if candidates else None,
            )
            if element is None:
                ok = False
                break
            from_screen = result.screens[from_fp]
            tap = selector_for(element, _owned(from_screen, app_package), from_screen.platform)
            landmark = _landmark(result.screens[to_fp])
            if tap is None or landmark is None:
                ok = False
                break
            # Fill this screen's form before advancing.
            fs = _form_steps(from_screen, app_package)
            form_steps += len(fs)
            steps.extend(fs)
            steps.append(Step(ActionType.TAP, selector=tap, description=f"Tap {edge.label}"))
            taps.append(edge.label)
            steps.append(
                Step(
                    ActionType.ASSERT,
                    selector=landmark,
                    assertion=AssertionType.VISIBLE,
                    description=f"Reached screen {edge.dst}",
                )
            )
        if not ok:
            continue
        # Fill the terminal screen's form too.
        terminal_forms = _form_steps(result.screens[fp_of[node_path[-1]]], app_package)
        form_steps += len(terminal_forms)
        steps.extend(terminal_forms)

        seen_paths.add(node_path)
        label = " → ".join(f"screen {n}" for n in node_path)
        # Name the journey after the controls it taps, so it reads like a story:
        # journey_from_transfer_to_confirm. Falls back to the path if labels are bare.
        from framework.crawler.to_codegen import _slug

        tap_slugs = [s for s in (_slug(t) for t in taps) if s]
        if len(tap_slugs) >= 2:
            journey = f"journey_from_{tap_slugs[0]}_to_{tap_slugs[-1]}"
        elif tap_slugs:
            journey = f"journey_via_{tap_slugs[0]}"
        else:
            journey = f"journey_{'_'.join(str(n) for n in node_path)}"
        case = TestCase(
            name=journey,
            steps=steps,
            description=f"Multi-step path ({len(node_path)} screens): {label}",
        )
        # Priority: deepest first, then most form interaction, then most hub traffic.
        hub_score = sum(degree.get(n, 0) for n in node_path)
        scored.append(((len(node_path), form_steps, hub_score), case))

    scored.sort(key=lambda sc: sc[0], reverse=True)
    return [case for _, case in scored[:max_cases]]


def _annotate_depth(graph: InteractionGraph) -> None:
    if graph.entry is None:
        return
    adj = graph._adj()
    depth = {graph.entry: 0}
    q = deque([graph.entry])
    while q:
        cur = q.popleft()
        for e in adj.get(cur, []):
            if e.dst not in depth:
                depth[e.dst] = depth[cur] + 1
                q.append(e.dst)
    for n in graph.nodes:
        n.depth = depth.get(n.id, -1)


# ---- exports ---------------------------------------------------------------
def _mm_escape(text: str) -> str:
    return text.replace('"', "&quot;").replace("\n", " ")[:40]


def to_mermaid(graph: InteractionGraph) -> str:
    """Mermaid flowchart — renders inline on GitHub and in a README."""
    out = ["```mermaid", "flowchart TD"]
    for n in graph.nodes:
        top = f"Screen {n.id}"
        sub = f"{n.toolkit}·{n.platform} · {n.element_count} el"
        shape_l, shape_r = ("([", "])") if n.is_entry else ("[", "]")
        out.append(f'    N{n.id}{shape_l}"{top}<br/>{sub}"{shape_r}')
    for e in graph.edges:
        lbl = _mm_escape(f"{e.action} {e.label} ({e.element_type})")
        out.append(f'    N{e.src} -->|"{lbl}"| N{e.dst}')
    # highlight unreachable / dead-end screens
    for nid in graph.dead_ends():
        out.append(f"    class N{nid} deadend;")
    out.append("    classDef deadend stroke-dasharray: 5 5;")
    out.append("```")
    return "\n".join(out)


def to_dot(graph: InteractionGraph) -> str:
    """Graphviz DOT."""
    out = ["digraph InteractionGraph {", "  rankdir=TB;", '  node [shape=box, fontname="Helvetica"];']
    for n in graph.nodes:
        shape = "doublecircle" if n.is_entry else "box"
        out.append(
            f'  N{n.id} [label="Screen {n.id}\\n{n.toolkit}·{n.platform} ({n.element_count} el)", shape={shape}];'
        )
    for e in graph.edges:
        lbl = f"{e.action} {e.label} ({e.element_type})".replace('"', "'")[:40]
        out.append(f'  N{e.src} -> N{e.dst} [label="{lbl}"];')
    out.append("}")
    return "\n".join(out)


def to_json(graph: InteractionGraph) -> str:
    return json.dumps(graph.to_dict(), indent=2)
