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
