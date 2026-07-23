"""
Real-app training/validation data for the element classifier.

The classifier ships trained on *synthetic* elements; the honest question the
audit raised is "how well does it do on real apps?". This module turns real crawl
output — the ``inventory.json`` a crawl writes — into labelled examples the
classifier can be validated against and trained on.

Ground truth comes from the widget class, which is authoritative on the platforms
we can label cleanly:

* **iOS (XCUITest):** the element type *is* the class — a ``Button`` is a button,
  a ``Switch`` a switch, a ``TextField`` an input. We keep only the classes that
  are unambiguous and skip structural chrome (windows, keyboards, bare "Other").
* **Android:** the framework class is messier, but the common widgets
  (``Button``, ``EditText``, ``CheckBox``, ``Switch``, ``ImageView`` …) still name
  their type, so we map those and skip the rest.

Because the label is derived from the class and the class is also the classifier's
strongest *feature*, iOS data is most valuable as a **real-app validation set** (a
faithful accuracy number) and as robustness signal for the non-class features
(size, position, text shape); genuinely hard, class-ambiguous cases need a
richer Android source (e.g. the RICO dataset) to move the needle on training.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from framework.model.enums import ElementType

# iOS XCUITest class (the crawler strips the "XCUIElementType" prefix) -> label.
# Only unambiguous types; everything else is skipped so labels stay clean.
IOS_CLASS_LABELS: Dict[str, ElementType] = {
    "Button": ElementType.BUTTON,
    "MenuItem": ElementType.BUTTON,
    "SegmentedControl": ElementType.BUTTON,
    "StaticText": ElementType.TEXT,
    "TextField": ElementType.INPUT,
    "SecureTextField": ElementType.INPUT,
    "SearchField": ElementType.INPUT,
    "Switch": ElementType.SWITCH,
    "Image": ElementType.IMAGE,
    "Icon": ElementType.IMAGE,
    "Cell": ElementType.LIST,
    "CollectionView": ElementType.LIST,
    "Table": ElementType.LIST,
    "WebView": ElementType.WEBVIEW,
}

# Android widget class (simple name, case-insensitive substring) -> label.
ANDROID_CLASS_LABELS = [
    ("checkbox", ElementType.CHECKBOX),  # before "button": CheckBox contains neither, keep explicit
    ("radio", ElementType.RADIO),
    ("switch", ElementType.SWITCH),
    ("toggle", ElementType.SWITCH),
    ("edittext", ElementType.INPUT),
    ("button", ElementType.BUTTON),
    ("imageview", ElementType.IMAGE),
    ("imagebutton", ElementType.BUTTON),
    ("textview", ElementType.TEXT),
    ("recyclerview", ElementType.LIST),
    ("listview", ElementType.LIST),
    ("webview", ElementType.WEBVIEW),
]


def _label_for(class_name: str, platform: str) -> Optional[ElementType]:
    """Ground-truth label from a widget class, or None if it can't be labelled
    cleanly (structural chrome, ambiguous containers)."""
    if not class_name:
        return None
    if platform == "ios":
        return IOS_CLASS_LABELS.get(class_name)
    simple = class_name.rsplit(".", 1)[-1].lower()  # androidx.­…​.Button -> button
    for needle, label in ANDROID_CLASS_LABELS:
        if needle in simple:
            return label
    return None


def _bounds_wh(bounds: Any) -> Dict[str, float]:
    """Inventory bounds are ``[x1, y1, x2, y2]``; return width/height."""
    if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
        x1, y1, x2, y2 = bounds
        return {"width": max(0, x2 - x1), "height": max(0, y2 - y1)}
    if isinstance(bounds, dict):
        return {"width": bounds.get("width", 0), "height": bounds.get("height", 0)}
    return {"width": 0, "height": 0}


def element_to_row(element: Dict[str, Any], platform: str) -> Optional[Dict[str, Any]]:
    """Turn one inventory element into a labelled training row (features + label),
    or None if its class can't be labelled cleanly."""
    class_name = element.get("class") or element.get("class_name") or ""
    label = _label_for(class_name, platform)
    if label is None:
        return None
    return {
        "class": class_name,
        "clickable": bool(element.get("clickable")),
        "text": element.get("text", "") or "",
        "content_desc": element.get("content_desc", "") or "",
        "resource_id": element.get("resource_id", "") or "",
        "bounds": _bounds_wh(element.get("bounds")),
        "label": label.value,
    }


def _row_key(row: Dict[str, Any]) -> tuple:
    """Identity for de-duplication — the same control repeats across screens and
    build types; counting it once keeps the set from skewing to common widgets."""
    b = row["bounds"]
    return (row["class"], row["content_desc"], row["text"], int(b["width"]), int(b["height"]))


def extract_from_inventory(path: Path) -> List[Dict[str, Any]]:
    """Labelled rows from a single crawl ``inventory.json``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows: List[Dict[str, Any]] = []
    for screen in data.get("screens", []):
        platform = screen.get("platform", "android")
        for element in screen.get("elements", []):
            row = element_to_row(element, platform)
            if row is not None:
                rows.append(row)
    return rows


# A small, curated set of real-app elements shipped with the package and blended
# into training so the model learns from real feature distributions, not just
# synthetic ones. Built by build_real_dataset() from crawled kits; absent -> the
# model is synthetic-only (still fine). NB: only clean-labelled sources belong
# here — never a deliberately-buggy app like ChaosBank, whose labels embed
# injected defects; that one is for validation / bug-finding, not training.
SHIPPED_DATASET = Path(__file__).resolve().parent / "data" / "real_elements.json"


def load_shipped_real_dataset() -> List[Dict[str, Any]]:
    """The curated real-app rows shipped for training, or [] if none is bundled."""
    if not SHIPPED_DATASET.exists():
        return []
    try:
        data: List[Dict[str, Any]] = json.loads(SHIPPED_DATASET.read_text(encoding="utf-8"))
        return data
    except (ValueError, OSError):
        return []


def build_real_dataset(kit_dirs: Iterable[Path], out: Path = SHIPPED_DATASET) -> int:
    """Extract labelled rows from crawled kits and write the shipped dataset.
    Returns the number of rows written. Feed it only clean-labelled apps."""
    rows = extract_from_kits(kit_dirs, dedupe=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(rows)


def extract_from_kits(kit_dirs: Iterable[Path], dedupe: bool = True) -> List[Dict[str, Any]]:
    """Labelled rows from many kit directories (each with an ``inventory.json``),
    de-duplicated by default so repeated chrome doesn't dominate."""
    rows: List[Dict[str, Any]] = []
    for kit in kit_dirs:
        inv = Path(kit) / "inventory.json"
        if inv.exists():
            rows.extend(extract_from_inventory(inv))
    if not dedupe:
        return rows
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for row in rows:
        key = _row_key(row)
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique
