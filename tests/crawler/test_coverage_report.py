"""Crawl-coverage artifact: an honest map of what the crawl reached vs what the kit tests
(reachable / unreachable / gated / dead-end screens; element + screen test coverage; gaps)."""

from framework.codegen.ir import ActionType, Platform, Selector, SelectorStrategy, Step, TestCase, TestModel
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.coverage_report import build_coverage
from framework.crawler.graph import build_graph


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
    return CrawlScreen(fp, els, platform="android")


def _model_tapping(*locators):
    """A one-case model that taps each given resource-id (so those elements read as covered)."""
    steps = [Step(action=ActionType.TAP, selector=Selector(SelectorStrategy.ID, loc)) for loc in locators]
    return TestModel(name="S", app_package="com.x", platform=Platform.ANDROID, cases=[TestCase(name="t", steps=steps)])


def _result_abc():
    # A(entry) -> B -> A ; C recorded but unreachable.
    a = _screen("A", [_btn("Go", "id/go")])
    b = _screen("B", [_btn("Back", "id/back")])
    c = _screen("C", [_btn("Orphan", "id/c")])
    res = CrawlResult(screens={"A": a, "B": b, "C": c})
    res.transitions = [("A", _btn("Go", "id/go"), "B"), ("B", _btn("Back", "id/back"), "A")]
    return res


def test_reach_is_classified_reachable_vs_unreachable():
    res = _result_abc()
    graph = build_graph(res, "com.x")
    cov = build_coverage(res, graph, _model_tapping("id/go"))
    assert cov.screens_total == 3
    assert cov.screens_reachable == 2  # A, B; C has no path
    assert len(cov.unreachable) == 1
    assert cov.unreachable[0].fingerprint == "C"


def test_element_and_screen_coverage_only_counts_referenced_locators():
    res = _result_abc()
    graph = build_graph(res, "com.x")
    # The model taps id/go (on A) but not id/back (on B) — so A is tested, B is not.
    cov = build_coverage(res, graph, _model_tapping("id/go"))
    tested = {s.fingerprint for s in cov.screens if s.tested}
    assert tested == {"A"}
    assert cov.screens_tested == 1
    assert cov.screen_coverage_pct() == 50  # 1 of 2 reachable
    assert cov.elements_covered == 1  # only id/go
    untested = {s.fingerprint for s in cov.screens_untested}
    assert untested == {"B"}  # reachable but no case touches it


def test_gated_screen_is_flagged_behind_auth():
    res = _result_abc()
    res.gated = {"B"}
    graph = build_graph(res, "com.x")
    cov = build_coverage(res, graph, _model_tapping("id/go"))
    assert {s.fingerprint for s in cov.gated} == {"B"}


def test_dead_end_is_flagged():
    # A -> B, B has no outgoing edge -> B is a dead-end.
    a = _screen("A", [_btn("Go", "id/go")])
    b = _screen("B", [_btn("Leaf", "id/leaf")])
    res = CrawlResult(screens={"A": a, "B": b})
    res.transitions = [("A", _btn("Go", "id/go"), "B")]
    graph = build_graph(res, "com.x")
    cov = build_coverage(res, graph, _model_tapping("id/go"))
    assert {s.fingerprint for s in cov.dead_ends} == {"B"}


def test_markdown_and_json_render_the_sections():
    res = _result_abc()
    graph = build_graph(res, "com.x")
    cov = build_coverage(res, graph, _model_tapping("id/go"))
    md = cov.to_markdown("com.x")
    assert "Crawl coverage — com.x" in md
    assert "Unreachable" in md  # C
    assert "Reachable but untested" in md  # B
    assert "All screens" in md  # the per-screen table
    import json

    data = json.loads(cov.to_json())
    assert data["screens_total"] == 3
    assert data["screen_coverage_pct"] == 50
    assert len(data["screens"]) == 3


def test_empty_crawl_does_not_divide_by_zero():
    res = CrawlResult(screens={})
    graph = build_graph(res, "com.x")
    cov = build_coverage(res, graph, TestModel(name="S", app_package="com.x", platform=Platform.ANDROID, cases=[]))
    assert cov.screen_coverage_pct() == 0
    assert cov.element_coverage_pct() == 0
    assert "Crawl coverage" in cov.to_markdown("com.x")
