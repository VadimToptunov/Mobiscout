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
``mobiscout ml create-universal-model -o ml_models/universal_element_classifier.pkl``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from framework.crawler.app_crawler import CrawlElement

logger = logging.getLogger(__name__)

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
    return Path(base) / "mobiscout" / "universal_element_classifier.pkl"


def _model_path() -> Path:
    """Explicit override wins; otherwise the user cache location."""
    override = os.environ.get("MOBISCOUT_ML_MODEL")
    return Path(override) if override else _cache_path()


def ensure_model(force: bool = False) -> Optional[Path]:
    """Make a trained model available, training one (~1 s, from synthetic data)
    into the cache on first use. Returns the model path, or None if unavailable
    (e.g. sklearn missing, or disabled via MOBISCOUT_ML_AUTOTRAIN=0).

    Called by the CLI so users get real ML transparently; the library layer
    (classify) never trains implicitly, so tests/imports stay fast."""
    if os.environ.get("MOBISCOUT_ML_AUTOTRAIN") == "0":
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
            # Blend in real-app elements (clean-labelled crawls) so the model sees
            # real feature distributions, not only synthetic ones.
            from framework.ml.real_data_extractor import load_shipped_real_dataset

            data.extend(load_shipped_real_dataset())
            clf = ElementClassifier()
            clf.train_from_data(data, test_size=0.2)
            clf.save_model(path)
        reset_cache()
        return path
    except Exception:
        # Training is best-effort and must never be fatal: a constrained env
        # (missing/oom sklearn, unwritable cache) degrades to the heuristic. Log
        # at debug so the cause is diagnosable without breaking a crawl.
        logger.debug("ensure_model: training failed; using heuristic", exc_info=True)
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


@dataclass(frozen=True)
class _Signals:
    """The normalised inputs the type rules read, gathered once per element.

    Attributes:
        cls: Lower-cased class name (Android class or iOS XCUIElementType*).
        desc: Lower-cased content-description (for button-ish keyword hints).
        clickable: Whether the element is clickable.
        text: The element's visible text (raw; truthiness matters).
        content_desc: The raw content-description (truthiness matters).
        scrollable: Whether the element scrolls (a generic scroller is a list).
        focusable: Whether the element takes focus (with password -> input).
        password: Whether the element is a masked/secure field.
    """

    cls: str
    desc: str
    clickable: bool
    text: str
    content_desc: str
    scrollable: bool
    focusable: bool
    password: bool


def _any(cls: str, *keys: str) -> bool:
    """True if any of ``keys`` is a substring of the (lower-cased) class name."""
    return any(k in cls for k in keys)


# Ordered type rules: the first whose predicate matches wins, so order encodes
# precedence. Specific interactive class names come first ("RadioButton" and
# "ToggleButton" also contain "button", so they must beat the generic button
# rule); then list/webview/image; then a *behavioural* fallback for generic
# containers (View/ViewGroup/Other/Compose) whose class name says nothing.
_RULES: List[Tuple[Callable[[_Signals], bool], str]] = [
    # --- specific interactive types, by class name ---
    (lambda s: _any(s.cls, "edittext", "textfield", "securetextfield", "searchfield", "input"), "input"),
    (lambda s: "checkbox" in s.cls, "checkbox"),
    (lambda s: "radio" in s.cls, "radio"),
    (lambda s: "switch" in s.cls or "toggle" in s.cls, "switch"),
    # SegmentedControl and MenuItem are tappable, button-like controls — found
    # misclassified as generic when validating against real ChaosBank elements.
    (lambda s: _any(s.cls, "button", "btn", "segmented", "menuitem"), "button"),
    (lambda s: _any(s.cls, "recycler", "listview", "collectionview", "tableview", "scrollview"), "list"),
    (lambda s: "webview" in s.cls, "webview"),
    (lambda s: "image" in s.cls or "icon" in s.cls, "image"),
    # A *non-clickable* text/label element is text; a clickable one is a tappable
    # label (a button/link), so it fails here and falls through to the button rule.
    (lambda s: _any(s.cls, "text", "label", "statictext") and not s.clickable, "text"),
    # --- behavioural fallback for generic containers ---
    (lambda s: s.scrollable, "list"),
    (lambda s: s.clickable and bool(s.text or "button" in s.desc or "btn" in s.desc or s.content_desc), "button"),
    (lambda s: s.focusable and s.password, "input"),
    (lambda s: bool(s.text) and not s.clickable, "text"),
]


def _heuristic(element: CrawlElement) -> str:
    """Rule-based type from class name + attributes. Covers Android and iOS
    (XCUIElementType* names) and is the reliable fallback for inputs/toggles.

    Args:
        element: The crawled element to classify.

    Returns:
        The element type label ("button", "input", …), or "generic" if no rule
        in :data:`_RULES` matches.
    """
    signals = _Signals(
        cls=(element.class_name or "").lower(),
        desc=(element.content_desc or "").lower(),
        clickable=element.clickable,
        text=element.text,
        content_desc=element.content_desc,
        scrollable=getattr(element, "scrollable", False),
        focusable=getattr(element, "focusable", False),
        password=getattr(element, "password", False),
    )
    for predicate, label in _RULES:
        if predicate(signals):
            return label
    return "generic"


def _feature_dict(element: CrawlElement) -> dict:
    return {
        "class": element.class_name,
        "text": element.text,
        "content_desc": element.content_desc,
        "resource-id": element.resource_id,
        "clickable": element.clickable,
        # Behavioural signals — what tells a generic container's real role apart.
        "scrollable": getattr(element, "scrollable", False),
        "focusable": getattr(element, "focusable", False),
        "checkable": getattr(element, "checkable", False),
        "password": getattr(element, "password", False),
        "enabled": getattr(element, "enabled", True),
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
