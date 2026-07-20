"""
Real, human-labelled Android training data from the RICO dataset.

RICO's *semantic annotations* label every UI node with a role (``componentLabel``)
independent of its Android class — so a generic ``FrameLayout`` tagged "Text
Button" is a labelled *hard case*, exactly the signal live crawls of modern
(Compose / custom-view) apps can't give us cleanly. Each node carries the class,
clickability, bounds and resource-id we feed the classifier, plus the ground-truth
role. This turns those into balanced, de-duplicated training rows.

Dataset: RICO v0.1 semantic annotations (interactionmining.org/rico), 66k real
Android screens. Not vendored (157 MB); build_rico_rows() runs over an extracted
copy and the curated output is merged into the shipped real_elements.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# RICO componentLabel -> our ElementType value. Only unambiguous roles are mapped;
# containers/chrome (Card, Toolbar, Drawer, Modal, Pager Indicator, …) are skipped
# so labels stay clean.
RICO_LABEL_MAP = {
    "Text": "text",
    "Image": "image",
    "Icon": "image",
    "Text Button": "button",
    "Input": "input",
    "Checkbox": "checkbox",
    "Radio Button": "radio",
    "On/Off Switch": "switch",
    "Web View": "webview",
    "List Item": "list",
}


def _bounds_wh(bounds: Any) -> Dict[str, float]:
    """RICO bounds are ``[x1, y1, x2, y2]``; return width/height."""
    if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
        x1, y1, x2, y2 = bounds
        return {"width": max(0, x2 - x1), "height": max(0, y2 - y1)}
    return {"width": 0, "height": 0}


def rico_node_to_row(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One RICO node -> a labelled training row, or None if its role isn't one we
    map cleanly (or it has no real size)."""
    label = RICO_LABEL_MAP.get(node.get("componentLabel", ""))
    if label is None:
        return None
    wh = _bounds_wh(node.get("bounds"))
    if wh["width"] <= 0 or wh["height"] <= 0:
        return None
    return {
        "class": node.get("class", "") or "",
        "clickable": bool(node.get("clickable")),
        "text": "",  # RICO strips text for privacy; class/behaviour/geometry carry the signal
        "content_desc": "",
        "resource_id": node.get("resource-id", "") or "",
        "bounds": wh,
        "label": label,
    }


def _walk(node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Yield every node in a RICO annotation tree, depth-first."""
    if isinstance(node, dict):
        yield node
        for child in node.get("children", []) or []:
            yield from _walk(child)


def _row_key(row: Dict[str, Any]) -> tuple:
    """Identity for de-duplication — RICO strips text, so same class + size +
    label is the same training row; count it once."""
    b = row["bounds"]
    return (row["class"], row["resource_id"], row["label"], int(b["width"]), int(b["height"]))


def build_rico_rows(
    rico_dir: Path,
    per_label_cap: int = 500,
    max_files: Optional[int] = 6000,
) -> List[Dict[str, Any]]:
    """Balanced, de-duplicated labelled rows from a directory of RICO semantic
    annotation JSONs.

    Args:
        rico_dir: directory holding ``*.json`` annotation files.
        per_label_cap: max rows per element type — RICO is dominated by Text/Image,
            so capping keeps the set balanced.
        max_files: stop after scanning this many files (None = all 66k).
    """
    per_label: Dict[str, int] = {}
    seen: set = set()
    rows: List[Dict[str, Any]] = []
    files = sorted(Path(rico_dir).glob("*.json"))
    if max_files is not None:
        files = files[:max_files]
    for path in files:
        if all(per_label.get(lbl, 0) >= per_label_cap for lbl in RICO_LABEL_MAP.values()):
            break
        try:
            tree = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for node in _walk(tree):
            row = rico_node_to_row(node)
            if row is None:
                continue
            if per_label.get(row["label"], 0) >= per_label_cap:
                continue
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            per_label[row["label"]] = per_label.get(row["label"], 0) + 1
            rows.append(row)
    return rows
