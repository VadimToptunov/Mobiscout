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

_UNSET = object()
_model = _UNSET  # cached classifier | None (None = unavailable, heuristic-only)


def _cache_path() -> Path:
    """Where the auto-provisioned model lives — a user cache dir, never the repo.

    The model is trained from code-generated synthetic data, so we ship the
    *recipe* (see ensure_model) and never commit a 5 MB binary. Training locally
    also sidesteps sklearn pickle-version fragility."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "mobile-test-recorder" / "universal_element_classifier.pkl"


def _model_path() -> Path:
    """Explicit override wins; otherwise the user cache location."""
    override = os.environ.get("OBSERVE_ML_MODEL")
    return Path(override) if override else _cache_path()


def ensure_model(force: bool = False) -> Optional[Path]:
    """Make a trained model available, training one (~1 s, from synthetic data)
    into the cache on first use. Returns the model path, or None if unavailable
    (e.g. sklearn missing, or disabled via OBSERVE_ML_AUTOTRAIN=0).

    Called by the CLI so users get real ML transparently; the library layer
    (classify) never trains implicitly, so tests/imports stay fast."""
    if os.environ.get("OBSERVE_ML_AUTOTRAIN") == "0":
        return _model_path() if _model_path().exists() else None
    path = _model_path()
    if path.exists() and not force:
        return path
    try:
        import json
        import warnings

        from framework.ml.element_classifier import ElementClassifier
        from framework.ml.universal_model import UniversalModelBuilder

        path.parent.mkdir(parents=True, exist_ok=True)
        with warnings.catch_warnings():  # rare synthetic classes -> sklearn noise
            warnings.simplefilter("ignore")
            dataset = UniversalModelBuilder().generate_training_data(
                output_path=path.parent / "training_data.json", samples_per_type=250
            )
            with open(dataset) as f:
                data = json.load(f)
            clf = ElementClassifier()
            clf.train_from_data(data, test_size=0.2)
            clf.save_model(path)
        reset_cache()
        return path
    except Exception:
        return None


def _load_model():
    """Lazily load the classifier once; None if unavailable (-> heuristic).
    Does NOT train — provisioning is an explicit ensure_model() call."""
    global _model
    if _model is not _UNSET:
        return _model
    path = _model_path()
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
