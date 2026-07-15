"""Structural invariants read off the interaction graph: unreachable screens,
dead-ends, and screens with no path back to the entry."""

from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.graph import build_graph
from framework.crawler.invariants import check_invariants, invariants_markdown


def _screen(fp, els):
    return CrawlScreen(fp, els, platform="android")


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


def _graph(screens, transitions):
    res = CrawlResult(screens=screens)
    res.transitions = transitions
    return build_graph(res, "com.x")


def test_clean_app_has_no_violations():
    # A -> B -> A : reachable, no dead-ends, can return.
    a, b = _screen("A", [_btn("Go", "id/go")]), _screen("B", [_btn("Back", "id/back")])
    g = _graph({"A": a, "B": b}, [("A", _btn("Go", "id/go"), "B"), ("B", _btn("Back", "id/back"), "A")])
    assert check_invariants(g) == []
    assert "No structural issues" in invariants_markdown(g)


def test_dead_end_and_no_return_flagged():
    # A -> B (B is a one-way dead-end: no way forward, no way back).
    a, b = _screen("A", [_btn("Go", "id/go")]), _screen("B", [_btn("Nothing", "id/x")])
    g = _graph({"A": a, "B": b}, [("A", _btn("Go", "id/go"), "B")])
    names = {v.name for v in check_invariants(g)}
    assert "dead_ends" in names
    assert "no_return_path" in names


def test_unreachable_screen_flagged():
    # C is recorded but no transition reaches it.
    a, b, c = (
        _screen("A", [_btn("Go", "id/go")]),
        _screen("B", [_btn("Back", "id/back")]),
        _screen("C", [_btn("x", "id/c")]),
    )
    g = _graph(
        {"A": a, "B": b, "C": c},
        [("A", _btn("Go", "id/go"), "B"), ("B", _btn("Back", "id/back"), "A")],
    )
    unreachable = next(v for v in check_invariants(g) if v.name == "unreachable_screens")
    assert 3 in unreachable.screens  # screen C (index 3)
    assert unreachable.severity == "error"


def test_pipeline_writes_invariants(tmp_path, monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")
    from framework.crawler.pipeline import build_kit

    a, b = _screen("A", [_btn("Go", "id/go")]), _screen("B", [_btn("Nothing", "id/x")])
    res = CrawlResult(screens={"A": a, "B": b})
    res.transitions = [("A", _btn("Go", "id/go"), "B")]
    summary = build_kit(res, {"package": "com.x", "targets": ["python_pytest"], "output": str(tmp_path)})
    assert (tmp_path / "invariants.md").exists()
    assert summary["invariants"] >= 1  # dead-end B is flagged
