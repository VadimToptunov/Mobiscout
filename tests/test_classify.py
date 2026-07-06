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
    monkeypatch.setenv("OBSERVE_ML_MODEL", "/definitely/nonexistent.pkl")
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
    ],
)
def test_heuristic_types(cls, expected):
    etype, conf, source = C.classify(_el(cls, text="x"))
    assert etype == expected
    assert source == "heuristic"


def test_button_by_content_desc_when_class_is_generic():
    etype, _, _ = C.classify(_el("android.view.View", desc="Login button"))
    assert etype == "button"


def test_unknown_is_generic():
    assert C.element_type(_el("android.view.ViewGroup", clickable=False)) == "generic"
