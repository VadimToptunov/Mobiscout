"""Coverage for the selector engine: scoring stability, building cross-platform
selectors with fallbacks, and optimising/analysing existing selectors. All pure
logic, previously ~11-18% covered."""

import pytest

from framework.model.app_model import Platform, Selector, SelectorStability as MS
from framework.selectors.selector_builder import SelectorBuilder
from framework.selectors.selector_optimizer import SelectorOptimizer
from framework.selectors.selector_scorer import SelectorScorer, SelectorStability

# --- SelectorScorer ---------------------------------------------------------


@pytest.fixture()
def scorer():
    return SelectorScorer()


@pytest.mark.parametrize(
    "selector,expected",
    [
        ({}, 0.0),
        ({"test_id": "x"}, 1.0),
        ({"accessibility_id": "x"}, 0.95),
        ({"resource_id": "x"}, 0.9),
        ({"text": "Login"}, 0.6),  # stable text
        ({"text": "Order 12345"}, 0.42),  # dynamic text -> 0.6 * 0.7
        ({"unknown_kind": "x"}, 0.3),  # unknown type falls back to 0.3
        ({"test_id": "x", "text": "y"}, 1.0),  # multi-attr bonus, capped at 1.0
    ],
)
def test_score_selector(scorer, selector, expected):
    assert scorer.score_selector(selector) == expected


def test_score_xpath_penalties_and_bonuses(scorer):
    deep = scorer.score_selector({"xpath": "//a/b/c/d/e/f"})  # depth>5 -> 0.3*0.7
    assert deep == 0.21
    with_attr = scorer.score_selector({"xpath": "//node[@resource-id='x']"})
    assert with_attr > deep  # attribute bonus outweighs the index penalty
    assert scorer._score_xpath("//" + "/".join("x" * 10)) <= 0.8  # capped


@pytest.mark.parametrize(
    "text,dynamic",
    [
        ("Login", False),
        ("Order 12345", True),  # 2+ digit run
        ("$19.99", True),  # currency
        ("ok", True),  # very short
        ("Submit", False),
    ],
)
def test_looks_dynamic(scorer, text, dynamic):
    assert scorer._looks_dynamic(text) is dynamic


@pytest.mark.parametrize(
    "score,level",
    [
        (0.95, SelectorStability.EXCELLENT),
        (0.8, SelectorStability.GOOD),
        (0.6, SelectorStability.FAIR),
        (0.4, SelectorStability.POOR),
        (0.1, SelectorStability.FRAGILE),
    ],
)
def test_get_stability_level(scorer, score, level):
    assert scorer.get_stability_level(score) == level


def test_recommend_fallbacks_orders_and_excludes_primary(scorer):
    fallbacks = scorer.recommend_fallbacks(
        primary_selector={"test_id": "login"},
        available_attributes={"test_id": "login", "resource_id": "btn", "text": "Login", "empty": ""},
    )
    keys = [list(f.keys())[0] for f in fallbacks]
    assert "test_id" not in keys  # primary excluded
    assert keys[0] == "resource_id"  # highest remaining score first
    assert len(fallbacks) <= 3


# --- SelectorBuilder --------------------------------------------------------


@pytest.fixture()
def builder():
    return SelectorBuilder()


def test_build_selector_prefers_test_tag(builder):
    sel = builder.build_selector("e1", {"test_tag": "login_btn"}, Platform.ANDROID)
    assert sel.android == "id:login_btn"
    assert sel.test_id == "login_btn"
    assert sel.stability == MS.HIGH


@pytest.mark.parametrize(
    "attributes,expected_android",
    [
        ({"resource_id": "com.x:id/go"}, "id:com.x:id/go"),
        ({"content_desc": "Go"}, "accessibility id:Go"),
        ({"text": "Tap me"}, "text:Tap me"),
        ({"class_name": "android.widget.Button"}, "//android.widget.Button"),
    ],
)
def test_android_priority_order(builder, attributes, expected_android):
    sel = builder.build_selector("e", attributes, Platform.ANDROID)
    assert sel.android == expected_android


def test_ios_selector_and_no_match(builder):
    sel = builder.build_selector("e", {"accessibility_id": "loginField"}, Platform.IOS)
    assert sel.ios == "accessibility id:loginField"
    # No usable attributes -> both platform selectors are None.
    empty = builder.build_selector("e", {}, Platform.ANDROID)
    assert empty.android is None and empty.ios is None


def test_determine_primary_strategy(builder):
    assert builder._determine_primary_strategy({"text": "x", "resource_id": "y"}) == "resource_id"
    assert builder._determine_primary_strategy({}) == "xpath"


def test_build_fallback_chain_excludes_primary_and_caps(builder):
    attrs = {"test_tag": "a", "resource_id": "b", "content_desc": "c", "text": "d"}
    chain = builder._build_fallback_chain(attrs, primary_strategy="test_id")
    assert "test_id" not in chain
    assert len(chain) <= 3


# --- SelectorOptimizer ------------------------------------------------------


@pytest.fixture()
def optimizer():
    return SelectorOptimizer()


def test_optimize_xpath_shortens_and_drops_default_index(optimizer):
    assert optimizer._optimize_xpath("//a/b/c/d/e[1]") == "//d/e"
    assert optimizer._optimize_xpath("") == ""
    # A shallow path is left alone (only the [1] default index is dropped).
    assert optimizer._optimize_xpath("//a/b[1]") == "//a/b"


def test_optimize_selector_rewrites_xpath(optimizer):
    sel = Selector(xpath="//a/b/c/d/e[1]")
    out = optimizer.optimize_selector(sel)
    assert out.xpath == "//d/e"


def test_analyze_selectors_empty_and_populated(optimizer):
    assert optimizer.analyze_selectors([])["total"] == 0

    selectors = [
        Selector(test_id="a", stability=MS.HIGH),
        Selector(xpath="//x", stability=MS.LOW),
        Selector(xpath="//y", stability=MS.LOW),
    ]
    report = optimizer.analyze_selectors(selectors)
    assert report["total"] == 3
    assert report["strategy_distribution"]["xpath"] == 2
    assert report["recommendations"]  # low-stability + xpath-heavy trigger advice


def test_find_duplicate_selectors(optimizer):
    selectors = [
        Selector(android="id:login"),
        Selector(android="id:login"),  # duplicate of index 0
        Selector(android="id:other"),
    ]
    dupes = optimizer.find_duplicate_selectors(selectors)
    assert (0, 1) in dupes


def test_suggest_improvements(optimizer):
    weak = Selector(xpath="//a", android="text:Hi", stability=MS.LOW)
    suggestions = optimizer.suggest_improvements(weak)
    text = " ".join(suggestions).lower()
    assert "xpath" in text
    assert any("stability" in s.lower() for s in suggestions)

    strong = Selector(
        test_id="x",
        android="id:x",
        ios="accessibility id:x",
        android_fallback=["a", "b"],
        ios_fallback=["c"],
        stability=MS.HIGH,
    )
    assert "looks good" in " ".join(optimizer.suggest_improvements(strong)).lower()
