"""Interaction graph: structure, analysis, and exports built from a crawl."""

import json

import pytest

from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler import graph as G


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def _btn(label, rid):
    return CrawlElement(
        resource_id=rid,
        text=label,
        content_desc="",
        class_name="android.widget.Button",
        clickable=True,
        bounds=(0, 0, 100, 50),
        package="com.x",
    )


def _screen(fp, els):
    return CrawlScreen(fingerprint=fp, elements=els, platform="android", toolkit="native")


def _result():
    res = CrawlResult(
        screens={
            "A": _screen("A", [_btn("Login", "id/login"), _btn("Help", "id/help")]),
            "B": _screen("B", [_btn("Catalog", "id/cat"), _btn("Back", "id/back")]),
            "C": _screen("C", [_btn("Buy", "id/buy")]),
            "D": _screen("D", [_btn("Profile", "id/prof")]),
        }
    )
    res.transitions = [
        ("A", _btn("Login", "id/login"), "B"),
        ("B", _btn("Catalog", "id/cat"), "C"),
        ("B", _btn("Back", "id/back"), "A"),  # A<->B cycle
        ("A", _btn("Help", "id/help"), "D"),
    ]
    return res


def test_metrics_and_analysis():
    g = G.build_graph(_result(), "com.x")
    m = g.metrics()
    assert m["screens"] == 4 and m["transitions"] == 4
    assert m["max_depth"] == 2  # A->B->C
    assert m["cycles"] == 1  # A<->B
    assert set(g.dead_ends()) == {3, 4}  # C and D have no outgoing edge
    assert g.unreachable() == []
    # entry is screen 1 at depth 0
    assert next(n for n in g.nodes if n.is_entry).depth == 0


def test_edges_are_typed_and_locatable():
    g = G.build_graph(_result(), "com.x")
    e = next(e for e in g.edges if e.label == "Login")
    assert e.element_type == "button"
    assert e.locator == "id=id/login"


def test_shortest_paths_and_edge_coverage():
    g = G.build_graph(_result(), "com.x")
    assert g.shortest_paths_from_entry()[3] == [1, 2, 3]
    walks = g.edge_coverage_paths()
    covered = {(e.src, e.dst) for w in walks for e in w}
    assert {(1, 2), (2, 3), (2, 1), (1, 4)} <= covered


def test_exports_render():
    g = G.build_graph(_result(), "com.x")
    mm = G.to_mermaid(g)
    assert "```mermaid" in mm and "flowchart TD" in mm and "N1 -->" in mm
    assert "digraph InteractionGraph" in G.to_dot(g)
    data = json.loads(G.to_json(g))
    assert data["metrics"]["screens"] == 4 and len(data["nodes"]) == 4


def _linear_result():
    """A -> B -> C -> D chain (a login->catalog->cart->pay style flow)."""
    res = CrawlResult(
        screens={
            "A": _screen("A", [_btn("Login", "id/login")]),
            "B": _screen("B", [_btn("Catalog", "id/cat")]),
            "C": _screen("C", [_btn("AddToCart", "id/add")]),
            "D": _screen("D", [_btn("Pay", "id/pay")]),
        }
    )
    res.transitions = [
        ("A", _btn("Login", "id/login"), "B"),
        ("B", _btn("Catalog", "id/cat"), "C"),
        ("C", _btn("AddToCart", "id/add"), "D"),
    ]
    return res


def test_multi_step_case_walks_the_full_path():
    cases = G.multi_step_cases(_linear_result(), "com.x")
    # only the maximal path survives (prefixes dropped); named after its taps
    assert len(cases) == 1 and cases[0].name.startswith("journey_")
    steps = cases[0].steps
    taps = [s for s in steps if s.action.value == "tap"]
    asserts = [s for s in steps if s.action.value == "assert"]
    assert len(taps) == 3 and len(asserts) == 3  # login, catalog, add-to-cart + a landmark each
    assert steps[0].action.value == "launch"


def test_multi_step_included_in_model():
    from framework.crawler.to_codegen import build_test_model

    model = build_test_model(_linear_result(), app_package="com.x")
    assert any(c.name.startswith("journey_") for c in model.cases)


def _el(cls, text="", rid="", desc="", clk=True):
    return CrawlElement(
        resource_id=rid,
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=clk,
        bounds=(0, 0, 300, 60),
        package="com.x",
    )


def test_paths_fill_forms_with_typed_samples():
    """A login screen along a path gets its inputs typed and checkbox toggled."""
    login = _screen(
        "A",
        [
            _el("android.widget.EditText", rid="com.x:id/email", desc="Email"),
            _el("android.widget.EditText", rid="com.x:id/password", desc="Password"),
            _el("android.widget.CheckBox", text="Remember me", rid="com.x:id/remember"),
            _el("android.widget.Button", text="Login", rid="com.x:id/login"),
        ],
    )
    res = CrawlResult(
        screens={
            "A": login,
            "B": _screen("B", [_btn("Catalog", "id/cat")]),
            "C": _screen("C", [_btn("Buy", "id/buy")]),
        }
    )
    res.transitions = [
        ("A", _el("android.widget.Button", text="Login", rid="com.x:id/login"), "B"),
        ("B", _btn("Catalog", "id/cat"), "C"),
    ]
    case = G.multi_step_cases(res, "com.x")[0]
    types = [s for s in case.steps if s.action.value == "type"]
    assert any(s.text == "test@example.com" for s in types)
    assert any(s.text == "Password123!" for s in types)
    assert any(s.action.value == "tap" and "Toggle" in s.description for s in case.steps)


def test_cycles_found_when_reachable_only_through_shared_node():
    """A cycle whose nodes are first reached via another branch must still be
    found. The old DFS marked nodes visited globally, so a cycle reachable only
    through an already-visited node (here C<->D, reached via B) was missed; the
    Tarjan SCC pass finds it."""
    res = CrawlResult(
        screens={
            "A": _screen("A", [_btn("toB", "id/b"), _btn("toC", "id/c")]),
            "B": _screen("B", [_btn("toC", "id/c2")]),
            "C": _screen("C", [_btn("toD", "id/d")]),
            "D": _screen("D", [_btn("toC", "id/c3")]),
        }
    )
    # A->B->C, A->C (so C is visited via the A->C branch first), then C<->D.
    res.transitions = [
        ("A", _btn("toB", "id/b"), "B"),
        ("A", _btn("toC", "id/c"), "C"),
        ("B", _btn("toC", "id/c2"), "C"),
        ("C", _btn("toD", "id/d"), "D"),
        ("D", _btn("toC", "id/c3"), "C"),
    ]
    g = G.build_graph(res, "com.x")
    cyclic_nodes = {n for comp in g.cycles() for n in comp}
    id_of = {n.fingerprint: n.id for n in g.nodes}
    assert {id_of["C"], id_of["D"]} <= cyclic_nodes  # C<->D cycle detected
    assert g.metrics()["cycles"] == 1


def test_cycles_deep_chain_does_not_recursionerror():
    """A long chain must not overflow the stack — the old recursive DFS did."""
    n = 3000
    screens = {str(i): _screen(str(i), [_btn("next", f"id/{i}")]) for i in range(n)}
    res = CrawlResult(screens=screens)
    res.transitions = [(str(i), _btn("next", f"id/{i}"), str(i + 1)) for i in range(n - 1)]
    res.transitions.append((str(n - 1), _btn("next", f"id/{n - 1}"), "0"))  # close the loop
    g = G.build_graph(res, "com.x")
    assert g.metrics()["cycles"] == 1  # the whole chain is one big SCC


def test_paths_prioritised_deepest_first():
    """With a shallow and a deep path, the deep one ranks first (survives the cap)."""
    res = CrawlResult(
        screens={
            "A": _screen("A", [_btn("Deep", "id/deep"), _btn("Shallow", "id/sh")]),
            "B": _screen("B", [_btn("On", "id/on")]),
            "C": _screen("C", [_btn("Buy", "id/buy")]),
            "D": _screen("D", [_btn("End", "id/end")]),
            "E": _screen("E", [_btn("Leaf", "id/leaf")]),
        }
    )
    res.transitions = [
        ("A", _btn("Deep", "id/deep"), "B"),
        ("B", _btn("On", "id/on"), "C"),
        ("C", _btn("Buy", "id/buy"), "D"),  # deep path A->B->C->D
        ("A", _btn("Shallow", "id/sh"), "E"),
        ("E", _btn("Leaf", "id/leaf"), "A"),  # shallow branch
    ]
    cases = G.multi_step_cases(res, "com.x", max_cases=1)
    assert len(cases) == 1
    assert cases[0].name.startswith("journey_")  # the deepest path won, named after its taps
