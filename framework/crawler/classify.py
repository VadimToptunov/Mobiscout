"""
Semantic element typing for the crawler — hybrid ML + heuristic.

The crawler locates elements; this module says *what each one is* (button,
input, checkbox, …) so the inventory is more useful and the codegen can emit
type-appropriate steps (e.g. type into an input, not just assert it visible).

Strategy — trust the ML classifier only when it is confident, fall back to a
robust rule heuristic otherwise:

* The RandomForest universal model is strong on buttons/text (~0.9 confidence)
  but weak on inputs/checkboxes; the class-name heuristic nails exactly those.
* So: ML wins when confidence >= ML_CONFIDENCE and it is not a vague "generic";
  otherwise the heuristic decides. This hybrid beats either alone.

The ML model is optional: if no model file is present the classifier is pure
heuristic, so a crawl never depends on shipping a binary. Generate one with
``observe ml create-universal-model -o ml_models/universal_element_classifier.pkl``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from framework.crawler.app_crawler import CrawlElement

# Confidence at/above which we trust the ML label over the heuristic.
ML_CONFIDENCE = 0.80

# Default model location; override with OBSERVE_ML_MODEL.
_DEFAULT_MODEL = "ml_models/universal_element_classifier.pkl"

_UNSET = object()
_model = _UNSET  # cached classifier | None (None = unavailable, heuristic-only)


def _load_model():
    """Lazily load the universal classifier once; None if unavailable."""
    global _model
    if _model is not _UNSET:
        return _model
    path = Path(os.environ.get("OBSERVE_ML_MODEL", _DEFAULT_MODEL))
    if not path.exists():
        _model = None
        return None
    try:
        from framework.ml.element_classifier import ElementClassifier

        clf = ElementClassifier()
        clf.load_model(path)
        _model = clf
    except Exception:
        # A broken/incompatible model must never break a crawl.
        _model = None
    return _model


def _heuristic(element: CrawlElement) -> str:
    """Rule-based type from class name + attributes. Covers Android and iOS
    (XCUIElementType* names) and is the reliable fallback for inputs/toggles."""
    cls = (element.class_name or "").lower()
    desc = (element.content_desc or "").lower()

    # Specific interactive types first — "RadioButton"/"ToggleButton" also
    # contain "button", so they must be matched before the generic button rule.
    if any(k in cls for k in ("edittext", "textfield", "securetextfield", "searchfield", "input")):
        return "input"
    if "checkbox" in cls:
        return "checkbox"
    if "radio" in cls:
        return "radio"
    if "switch" in cls or "toggle" in cls:
        return "switch"
    if "button" in cls or "btn" in cls:
        return "button"
    if any(k in cls for k in ("recycler", "listview", "collectionview", "tableview", "scrollview")):
        return "list"
    if "webview" in cls:
        return "webview"
    if "image" in cls or "icon" in cls:
        return "image"
    if "text" in cls or "label" in cls or "statictext" in cls:
        return "text"
    if element.clickable and ("button" in desc or "btn" in desc):
        return "button"
    return "generic"


def _feature_dict(element: CrawlElement) -> dict:
    return {
        "class": element.class_name,
        "text": element.text,
        "content_desc": element.content_desc,
        "resource-id": element.resource_id,
        "clickable": element.clickable,
    }


def classify(element: CrawlElement) -> Tuple[str, float, str]:
    """Return (element_type, confidence, source) where source is 'ml' or
    'heuristic'. ML is used only when present and confident."""
    heuristic_type = _heuristic(element)
    model = _load_model()
    if model is None:
        return heuristic_type, 1.0, "heuristic"
    try:
        ml_type, conf = model.predict(_feature_dict(element))
        ml_value = getattr(ml_type, "value", str(ml_type))
    except Exception:
        return heuristic_type, 1.0, "heuristic"
    if conf >= ML_CONFIDENCE and ml_value != "generic":
        return ml_value, float(conf), "ml"
    return heuristic_type, float(conf), "heuristic"


def element_type(element: CrawlElement) -> str:
    """Just the type label (convenience)."""
    return classify(element)[0]


def reset_cache() -> Optional[object]:
    """Test hook: forget the cached model so a new path is picked up."""
    global _model
    _model = _UNSET
    return None
