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
