"""Interaction graph: structure, analysis, and exports built from a crawl."""

import json

import pytest

from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler import graph as G


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("OBSERVE_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("OBSERVE_ML_MODEL", "/nonexistent.pkl")


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
