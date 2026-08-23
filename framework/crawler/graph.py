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

from framework.codegen.ir import ActionType, AssertionType, Selector, Step, TestCase
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.classify import classify
from framework.crawler.form_values import _SUBMIT_LABELS, _invalid_value, _sample_value
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
    edge_case: Optional[str] = None  # error/loading/permission/network screen, if flagged

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
            "edge_case": self.edge_case,
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
    # Adjacency is derived from ``edges`` (immutable once the graph is built) and
    # read by nearly every analysis (dead_ends, cycles, shortest paths, edge
    # coverage, depth, metrics, invariants), so it is built once and cached rather
    # than rebuilt on each call. Excluded from init/repr/eq — it's pure derived state.
    _adj_cache: Optional[Dict[int, List[GraphEdge]]] = field(default=None, init=False, repr=False, compare=False)

    # ---- adjacency helpers -------------------------------------------------
    def _adj(self) -> Dict[int, List[GraphEdge]]:
        """Source-indexed adjacency, computed once and reused. Callers only read
        via ``.get(...)`` (never index-assign), so the shared dict is safe."""
        if self._adj_cache is None:
            adj: Dict[int, List[GraphEdge]] = defaultdict(list)
            for e in self.edges:
                adj[e.src].append(e)
            self._adj_cache = adj
        return self._adj_cache

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
        """Cyclic strongly-connected components, each returned as its member node
        ids. Computed with an iterative Tarjan SCC pass, which (unlike the old
        recursive DFS back-edge walk with a single global ``visited`` set) finds
        *every* cycle — including ones reachable only through an already-visited
        node — and never overflows the recursion stack on a deep graph. A component
        is cyclic iff it has more than one node, or a single node with a self-loop.
        """
        adj = self._adj()
        index_of: Dict[int, int] = {}
        lowlink: Dict[int, int] = {}
        on_stack: set = set()
        scc_stack: List[int] = []
        sccs: List[List[int]] = []
        counter = 0

        # Iterative Tarjan: each work-stack frame is (node, next-edge-index). The
        # index lets us resume a node's edge scan after descending into a child,
        # exactly as the recursive call would — but on the heap, so depth is free.
        for root in (n.id for n in self.nodes):
            if root in index_of:
                continue
            work: List[Tuple[int, int]] = [(root, 0)]
            while work:
                node, i = work[-1]
                if i == 0:  # first visit to this node
                    index_of[node] = lowlink[node] = counter
                    counter += 1
                    scc_stack.append(node)
                    on_stack.add(node)
                edges = adj.get(node, [])
                recursed = False
                while i < len(edges):
                    dst = edges[i].dst
                    i += 1
                    if dst not in index_of:
                        work[-1] = (node, i)  # resume here after the child returns
                        work.append((dst, 0))
                        recursed = True
                        break
                    if dst in on_stack:
                        lowlink[node] = min(lowlink[node], index_of[dst])
                if recursed:
                    continue
                if lowlink[node] == index_of[node]:  # root of an SCC
                    comp: List[int] = []
                    while True:
                        w = scc_stack.pop()
                        on_stack.discard(w)
                        comp.append(w)
                        if w == node:
                            break
                    sccs.append(comp)
                work.pop()
                if work:  # propagate lowlink up to the parent (post-recursion update)
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])

        self_looped = {e.src for e in self.edges if e.src == e.dst}
        return [c for c in sccs if len(c) > 1 or (c and c[0] in self_looped)]

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
            path: List[int] = []
            cur2: Optional[int] = node
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


# Keyword → edge-case screen kind, harvested from the former flow.flow_discovery.
# Only high-signal, text-based kinds are kept; its count-based "empty_state" is
# dropped as too noisy for real screens (many legit screens have 1–2 controls).
_EDGE_CASE_KEYWORDS = (
    ("error_screen", ("error", "failed", "went wrong", "crash")),
    ("loading_screen", ("loading", "please wait", "in progress")),
    ("permission_dialog", ("permission", "allow ", "grant", "deny")),
    ("network_error", ("no connection", "offline", "network error", "no internet")),
)


def _classify_screen(screen: CrawlScreen) -> Optional[str]:
    """Flag a special screen (error / loading / permission / network) from its
    element texts, so the interaction graph and its report call out screens a
    tester should treat specially. None for an ordinary screen."""
    texts = " ".join(f"{e.text} {e.content_desc}" for e in screen.elements).lower()
    for kind, keywords in _EDGE_CASE_KEYWORDS:
        if any(keyword in texts for keyword in keywords):
            return kind
    return None


def navigation_steps(
    result: CrawlResult, app_package: str = "", graph: Optional[InteractionGraph] = None
) -> Dict[str, List[Step]]:
    """The TAP steps that reach each screen from the entry (empty list for the
    entry itself). A per-screen state check uses this to *navigate to* the screen
    before asserting its controls — otherwise it would assert a deeper screen's
    elements right after launch (which only shows the entry screen) and fail on a
    real device. Screens with no path from the entry are omitted (unreachable ⇒
    not state-testable), so the dict's keys are exactly the screens worth checking.

    ``graph`` may be a pre-built interaction graph for this same crawl; when given
    it is reused instead of rebuilt (the graph is deterministic for a given
    result/package, so the output is identical).
    """
    graph = graph if graph is not None else build_graph(result, app_package)
    fps = list(result.screens)
    if not fps:
        return {}
    fp_of = {i + 1: fp for i, fp in enumerate(fps)}  # node id (1-based) -> fingerprint
    entry_fp = fp_of.get(graph.entry if graph.entry is not None else 1, fps[0])

    by_pair: Dict[Tuple[str, str], List[CrawlElement]] = defaultdict(list)
    for t in result.transitions:
        if getattr(t, "kind", "tap") == "probe":
            continue  # a negative-data probe is not a real navigation
        from_fp, elem, to_fp = t
        by_pair[(from_fp, to_fp)].append(elem)

    reachable: Dict[str, List[Step]] = {entry_fp: []}
    if graph.entry is None:
        return reachable  # no navigation model — only the entry screen is testable

    gated = getattr(result, "gated", None) or set()
    for node_id, path in graph.shortest_paths_from_entry().items():
        target_fp = fp_of.get(node_id)
        if target_fp is None or target_fp == entry_fp:
            continue
        # For a screen behind a gate, codegen prepends the auth steps, which land
        # the test on the post-auth home — so navigate only the in-app hops from
        # there, trimming the path (and its synthetic gate-crossing hop) to start at
        # the first gated node. Without this the nav would re-tap from the launcher.
        if target_fp in gated:
            first_gated = next((i for i, n in enumerate(path) if fp_of.get(n) in gated), None)
            if first_gated:
                path = path[first_gated:]
        steps: List[Step] = []
        ok = True
        for a, b in zip(path, path[1:]):
            src_fp = fp_of.get(a)
            dst_fp = fp_of.get(b)
            if src_fp is None or dst_fp is None:
                ok = False
                break
            elems = by_pair.get((src_fp, dst_fp), [])
            screen = result.screens.get(src_fp)
            selector = None
            for elem in elems:
                owned = _owned(screen, app_package) if screen else None
                selector = selector_for(elem, owned, screen.platform if screen else "android")
                if selector:
                    break
            if selector is None:
                ok = False  # can't build a locator for a hop — drop this screen
                break
            label = (elems[0].label or elems[0].class_name) if elems else "element"
            steps.append(Step(ActionType.TAP, selector=selector, description=f"Navigate: tap {label}"))
        if ok:
            reachable[target_fp] = steps
    return reachable


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
                edge_case=_classify_screen(screen),
            )
        )

    edges: List[GraphEdge] = []
    seen = set()
    for t in result.transitions:
        if getattr(t, "kind", "tap") == "probe":
            continue  # negative-data probes never become graph edges / positive journeys
        from_fp, element, to_fp = t
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


def multi_step_cases(
    result: CrawlResult, app_package: str = "", max_cases: int = 12, graph: Optional[InteractionGraph] = None
) -> List[TestCase]:
    """Model-based test cases: walk real paths through the interaction graph.

    Beyond navigating (login -> catalog -> cart -> pay), each screen along the way
    has its form filled — inputs get sample data, checkboxes/switches get toggled —
    so the paths exercise forms too. Paths are prioritised deepest/most-critical
    first, then capped, so the most valuable ones survive max_cases.

    ``graph`` may be a pre-built interaction graph for this same crawl; reused when
    given (deterministic, so output is identical) instead of rebuilt.
    """
    graph = graph if graph is not None else build_graph(result, app_package)
    fps = list(result.screens)
    fp_of = {i + 1: fp for i, fp in enumerate(fps)}
    gated = getattr(result, "gated", None) or set()
    degree = {n.id: 0 for n in graph.nodes}
    for e in graph.edges:
        degree[e.src] = degree.get(e.src, 0) + 1
        degree[e.dst] = degree.get(e.dst, 0) + 1

    by_pair: Dict[Tuple[str, str], List] = defaultdict(list)
    for from_fp, elem, to_fp in result.transitions:
        by_pair[(from_fp, to_fp)].append(elem)

    def _landmark(screen: CrawlScreen) -> Optional[Selector]:
        owned = _owned(screen, app_package)
        return next((s for s in (selector_for(e, owned, screen.platform) for e in owned) if s), None)

    # Keep only maximal walks (drop those that are a strict prefix of a longer one).
    # edge_coverage_paths() is computed once and reused (it was previously called
    # twice). Maximality is found in O(sum of path lengths) instead of O(n^2): a
    # path is non-maximal iff it is a proper prefix of another path, so we mark
    # every proper prefix that is itself a path and subtract that set.
    all_walks = graph.edge_coverage_paths()
    raw_paths = [tuple([w[0].src] + [e.dst for e in w]) for w in all_walks if len(w) >= 2]
    path_set = set(raw_paths)
    non_maximal = set()
    for p in path_set:
        for k in range(1, len(p)):
            prefix = p[:k]
            if prefix in path_set:
                non_maximal.add(prefix)
    maximal = path_set - non_maximal

    scored: List[Tuple[tuple, TestCase]] = []
    seen_paths = set()
    for walk in all_walks:
        if len(walk) < 2:
            continue
        node_path = tuple([walk[0].src] + [e.dst for e in walk])
        if node_path in seen_paths or node_path not in maximal:
            continue
        # Skip journeys that cross into a gated screen: reaching it needs the auth
        # prefix (login/OTP), which the per-screen auth-prefixed cases already cover.
        # A bare journey here would fill the gate form with sample data and assert the
        # post-auth screen — red on any app whose gate actually gates.
        if any(fp_of.get(n) in gated for n in node_path):
            continue

        steps: List[Step] = [Step(ActionType.LAUNCH, description="Open app")]
        form_steps = 0
        taps: List[str] = []
        ok = True
        for edge in walk:
            from_fp, to_fp = fp_of[edge.src], fp_of[edge.dst]
            candidates = by_pair.get((from_fp, to_fp), [])
            element: Optional[CrawlElement] = next(
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
        # journey_from_transfer_to_confirm. A label-less Compose wrapper is only a
        # bare framework class ("android.view.View" -> android_view_view), which
        # names nothing — drop those and fall back to the destination screen's title
        # (journey_to_checkout), then the path.
        from framework.crawler.to_codegen import _screen_title, _slug  # _owned is module-level

        tap_slugs = [s for s in (_slug(t) for t in taps) if s and not s.startswith("android_")]
        dest_screen = result.screens.get(fp_of[node_path[-1]])
        dest_title = _slug(_screen_title(_owned(dest_screen, app_package))) if dest_screen else ""
        if len(tap_slugs) >= 2:
            journey = f"journey_from_{tap_slugs[0]}_to_{tap_slugs[-1]}"
        elif tap_slugs:
            journey = f"journey_via_{tap_slugs[0]}"
        elif dest_title:
            journey = f"journey_to_{dest_title}"
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


def _submit_element(screen: CrawlScreen, app_package: str) -> Optional[CrawlElement]:
    """The button on this screen that commits a form (login/continue/…), or None."""
    for e in _owned(screen, app_package):
        if not e.clickable or classify(e)[0] != "button":
            continue
        label = (e.text or e.content_desc or e.resource_id or "").strip().lower()
        if any(k in label for k in _SUBMIT_LABELS):
            return e
    return None


def _invalid_form_steps(screen: CrawlScreen, app_package: str) -> List[Step]:
    """TYPE steps that fill a screen's inputs with *invalid* data. Empty if no
    field has a meaningful invalid value (so the caller can skip the case)."""
    steps: List[Step] = []
    owned = _owned(screen, app_package)
    seen = set()
    for e in owned:
        if classify(e)[0] != "input":
            continue
        value = _invalid_value(e)
        if not value:
            continue
        sel = selector_for(e, owned, screen.platform)
        if sel is None or sel.value in seen:
            continue
        seen.add(sel.value)
        steps.append(
            Step(ActionType.TYPE, selector=sel, text=value, description=f"Type invalid data into {e.label or 'input'}")
        )
    return steps


def negative_form_cases(
    result: CrawlResult, app_package: str = "", max_cases: int = 12, graph: Optional[InteractionGraph] = None
) -> List[TestCase]:
    """Negative-path tests: for each screen with a submittable form (input +
    submit control), navigate to it, type *invalid* data, submit, and assert the
    app *rejects* it — the submit control is still visible, i.e. the form did not
    advance. A correct app stays put; a buggy one advances and fails the test,
    which is exactly the validation defect we want caught.

    This is the negative counterpart to the positive form-filling already done by
    :func:`multi_step_cases`; together they cover both branches of every form.

    ``graph`` may be a pre-built interaction graph for this same crawl; reused when
    given (deterministic, so output is identical) instead of rebuilt.
    """
    graph = graph if graph is not None else build_graph(result, app_package)
    paths = graph.shortest_paths_from_entry()
    if not paths:
        return []
    fps = list(result.screens)
    fp_of = {i + 1: fp for i, fp in enumerate(fps)}
    id_of = {fp: i + 1 for i, fp in enumerate(fps)}

    by_pair: Dict[Tuple[str, str], List] = defaultdict(list)
    for from_fp, elem, to_fp in result.transitions:
        by_pair[(from_fp, to_fp)].append(elem)

    from framework.crawler.to_codegen import _screen_title, _slug

    cases: List[TestCase] = []
    for target_fp, screen in result.screens.items():
        submit = _submit_element(screen, app_package)
        if submit is None:
            continue
        invalid_steps = _invalid_form_steps(screen, app_package)
        if not invalid_steps:
            continue  # no strongly-typed field to make invalid — skip
        submit_sel = selector_for(submit, _owned(screen, app_package), screen.platform)
        if submit_sel is None:
            continue
        node_path = paths.get(id_of.get(target_fp, -1))
        if node_path is None:
            continue  # form screen unreachable from entry

        # Reconstruct the navigation taps to reach the form screen.
        steps: List[Step] = [Step(ActionType.LAUNCH, description="Open app")]
        ok = True
        for src_id, dst_id in zip(node_path, node_path[1:]):
            from_fp, to_fp = fp_of[src_id], fp_of[dst_id]
            candidates = by_pair.get((from_fp, to_fp), [])
            if not candidates:
                ok = False
                break
            from_screen = result.screens[from_fp]
            tap = selector_for(candidates[0], _owned(from_screen, app_package), from_screen.platform)
            if tap is None:
                ok = False
                break
            steps.append(Step(ActionType.TAP, selector=tap, description=f"Tap {candidates[0].label}"))
        if not ok:
            continue

        steps.extend(invalid_steps)
        steps.append(Step(ActionType.TAP, selector=submit_sel, description=f"Submit {submit.label or 'form'}"))
        steps.append(
            Step(
                ActionType.ASSERT,
                selector=submit_sel,
                assertion=AssertionType.VISIBLE,
                description="Invalid input is rejected — the form did not advance",
            )
        )
        title = _slug(_screen_title(_owned(screen, app_package))) or _slug(submit.label or "") or "form"
        cases.append(
            TestCase(
                name=f"rejects_invalid_input_on_{title}",
                steps=steps,
                description=f"Submitting invalid data on the {title.replace('_', ' ')} form is rejected",
            )
        )
        if len(cases) >= max_cases:
            break
    return cases


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
