"""RICO semantic annotations -> labelled Android training rows: roles mapped from
componentLabel (independent of the Android class, so generic containers get clean
labels), containers skipped, balanced + de-duplicated."""

import json

from framework.ml.rico_extractor import RICO_LABEL_MAP, build_rico_rows, rico_node_to_row


def test_component_label_maps_to_our_type_regardless_of_class():
    # a generic FrameLayout that RICO labels a Text Button -> a labelled hard case
    row = rico_node_to_row(
        {
            "componentLabel": "Text Button",
            "class": "android.widget.FrameLayout",
            "clickable": True,
            "bounds": [0, 0, 200, 80],
        }
    )
    assert row["label"] == "button" and row["class"] == "android.widget.FrameLayout"
    assert row["bounds"] == {"width": 200, "height": 80}


def test_unmapped_roles_and_zero_size_are_skipped():
    assert rico_node_to_row({"componentLabel": "Toolbar", "bounds": [0, 0, 100, 50]}) is None  # container role
    assert rico_node_to_row({"componentLabel": "Text", "bounds": [0, 0, 0, 0]}) is None  # no size


def test_core_roles_are_covered():
    for role in ("Text", "Image", "Text Button", "Input", "On/Off Switch", "Web View"):
        assert role in RICO_LABEL_MAP


def test_build_rico_rows_balances_and_dedupes(tmp_path):
    # one screen with many identical Text nodes + a couple of buttons
    tree = {
        "componentLabel": "Toolbar",
        "bounds": [0, 0, 400, 800],
        "children": [
            {"componentLabel": "Text", "class": "android.widget.TextView", "bounds": [0, 0, 100, 40]},
            {"componentLabel": "Text", "class": "android.widget.TextView", "bounds": [0, 0, 100, 40]},  # identical -> dup
            {"componentLabel": "Text", "class": "android.widget.TextView", "bounds": [0, 50, 130, 110]},  # 130x60
            {
                "componentLabel": "Text Button",
                "class": "android.view.View",
                "clickable": True,
                "bounds": [0, 100, 200, 160],
            },
        ],
    }
    (tmp_path / "1.json").write_text(json.dumps(tree), encoding="utf-8")
    rows = build_rico_rows(tmp_path, per_label_cap=10)
    labels = [r["label"] for r in rows]
    assert labels.count("text") == 2  # the duplicate was dropped
    assert labels.count("button") == 1


def test_per_label_cap_limits_dominant_classes(tmp_path):
    # distinct sizes so none dedupe away — the cap, not dedup, does the limiting
    kids = [{"componentLabel": "Text", "class": "T", "bounds": [0, 0, 100 + i, 40]} for i in range(20)]
    (tmp_path / "1.json").write_text(json.dumps({"componentLabel": "Toolbar", "children": kids}), encoding="utf-8")
    rows = build_rico_rows(tmp_path, per_label_cap=5)
    assert sum(1 for r in rows if r["label"] == "text") == 5
