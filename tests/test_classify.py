"""Hybrid element typing: heuristic must be correct on its own (no model), and
the ML model is only trusted when confident. Tests run model-free (CI ships no
.pkl), exercising the heuristic path that every crawl falls back to."""

import pytest

from framework.crawler import classify as C
from framework.crawler.app_crawler import CrawlElement


def _el(cls, text="", desc="", clickable=True):
    return CrawlElement(
        resource_id="", text=text, content_desc=desc, class_name=cls, clickable=clickable, bounds=(0, 0, 100, 50)
    )


@pytest.fixture(autouse=True)
def _no_model(monkeypatch):
    # Force heuristic-only regardless of any locally generated model.
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/definitely/nonexistent.pkl")
    C.reset_cache()
    yield
    C.reset_cache()


@pytest.mark.parametrize(
    "cls,expected",
    [
        ("android.widget.Button", "button"),
        ("android.widget.EditText", "input"),
        ("XCUIElementTypeSecureTextField", "input"),
        ("XCUIElementTypeButton", "button"),
        ("android.widget.CheckBox", "checkbox"),
        ("android.widget.Switch", "switch"),
        # ToggleButton contains both "toggle" and "button" — the switch rule must
        # win over the generic button rule (ordering in the rule table).
        ("android.widget.ToggleButton", "switch"),
        ("android.widget.RadioButton", "radio"),
        ("androidx.recyclerview.widget.RecyclerView", "list"),
        ("android.webkit.WebView", "webview"),
        ("android.widget.ImageView", "image"),
        ("XCUIElementTypeStaticText", "text"),
        # SegmentedControl / MenuItem are tappable button-like controls — caught
        # by validating the classifier against real ChaosBank elements.
        ("XCUIElementTypeSegmentedControl", "button"),
        ("XCUIElementTypeMenuItem", "button"),
    ],
)
def test_heuristic_types(cls, expected):
    # Interactive types are clickable; text/image/list are not (a *clickable*
    # text element is a tappable label -> button, which is a separate case).
    clickable = expected in ("button", "input", "checkbox", "switch", "radio")
    etype, conf, source = C.classify(_el(cls, text="x", clickable=clickable))
    assert etype == expected
    assert source == "heuristic"


def test_button_by_content_desc_when_class_is_generic():
    etype, _, _ = C.classify(_el("android.view.View", desc="Login button"))
    assert etype == "button"


@pytest.mark.parametrize(
    "cls,kwargs,expected",
    [
        # Generic containers whose *behaviour* reveals the role (the hard cases).
        ("android.view.View", {"clickable": True, "text": "Buy"}, "button"),
        ("android.widget.FrameLayout", {"clickable": True, "desc": "Add"}, "button"),
        ("XCUIElementTypeOther", {"clickable": True, "text": "Confirm"}, "button"),
        ("XCUIElementTypeStaticText", {"clickable": True, "text": "See all"}, "button"),  # tappable label
        ("android.view.ViewGroup", {"clickable": False, "scrollable": True}, "list"),
        ("XCUIElementTypeOther", {"clickable": False, "scrollable": True}, "list"),
        ("android.view.View", {"clickable": False, "text": "Total balance"}, "text"),
        ("android.view.View", {"clickable": True, "focusable": True, "password": True}, "input"),
        ("android.view.View", {"clickable": False}, "generic"),  # nothing to go on -> generic
    ],
)
def test_generic_containers_classified_by_behaviour(cls, kwargs, expected):
    el = CrawlElement(
        resource_id="",
        text=kwargs.get("text", ""),
        content_desc=kwargs.get("desc", ""),
        class_name=cls,
        clickable=kwargs.get("clickable", False),
        bounds=(0, 0, 200, 60),
        scrollable=kwargs.get("scrollable", False),
        focusable=kwargs.get("focusable", False),
        password=kwargs.get("password", False),
    )
    assert C.classify(el)[0] == expected


def test_unknown_is_generic():
    assert C.element_type(_el("android.view.ViewGroup", clickable=False)) == "generic"


# --- batch classification (perf: one model round-trip, cache pre-warm) ----------------


def test_classify_many_matches_per_element_and_warms_the_cache(monkeypatch):
    els = [
        _el("android.widget.Button", text="Go"),
        _el("android.widget.EditText", desc="Email"),
        _el("android.widget.CheckBox", text="x"),
    ]
    single = [C.classify(e) for e in els]
    C.reset_cache()

    C.classify_many(els)
    # Every element is now cached, so classify recomputes nothing — a hit returns the memo.
    calls = {"n": 0}
    original = C._classify_uncached
    monkeypatch.setattr(C, "_classify_uncached", lambda e: calls.__setitem__("n", calls["n"] + 1) or original(e))
    batched = [C.classify(e) for e in els]
    assert calls["n"] == 0  # no recomputation — served from the warmed cache
    assert batched == single  # heuristic path: identical results


def test_classify_many_is_a_noop_on_empty_and_deduplicates(monkeypatch):
    C.classify_many([])  # must not raise
    # Two elements with identical fields share one cache entry / one model row.
    a = _el("android.widget.Button", text="Same")
    b = _el("android.widget.Button", text="Same")
    C.classify_many([a, b])
    assert C._classify_key(a) in C._classify_cache


def test_classify_many_uses_a_single_batch_model_call_when_a_model_is_present(monkeypatch):
    # Inject a fake model exposing predict_batch; classify_many must call it ONCE for all
    # elements (the whole point — amortise sklearn/pandas per-call overhead), not per element.
    # A plain-string label exercises the getattr(ml_type, "value", str(ml_type)) path without
    # importing the ML module (CI runs without the ml extra).
    calls = {"batch": 0, "rows": 0}

    class _FakeModel:
        def predict_batch(self, feats):
            calls["batch"] += 1
            calls["rows"] += len(feats)
            return [("button", 0.99) for _ in feats]

    monkeypatch.setattr(C, "_load_model", lambda: _FakeModel())
    C.reset_cache()
    els = [_el("android.widget.Button", text=f"b{i}") for i in range(5)]
    C.classify_many(els)
    assert calls["batch"] == 1 and calls["rows"] == 5  # one call, all rows
    assert all(C.classify(e)[0] == "button" for e in els)  # confident ML label applied
