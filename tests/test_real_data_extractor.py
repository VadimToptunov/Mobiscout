"""Turning real crawl inventory into labelled classifier data: clean ground-truth
labels from the widget class, structural chrome skipped, repeats de-duplicated."""

import json

from framework.ml.real_data_extractor import (
    build_real_dataset,
    element_to_row,
    extract_from_inventory,
    extract_from_kits,
    load_shipped_real_dataset,
)


def test_ios_classes_get_clean_ground_truth_labels():
    assert element_to_row({"class": "Button", "clickable": True}, "ios")["label"] == "button"
    assert element_to_row({"class": "Switch"}, "ios")["label"] == "switch"
    assert element_to_row({"class": "TextField"}, "ios")["label"] == "input"
    assert element_to_row({"class": "StaticText", "text": "Balance"}, "ios")["label"] == "text"
    assert element_to_row({"class": "CollectionView"}, "ios")["label"] == "list"


def test_structural_chrome_is_skipped():
    for chrome in ("Other", "Window", "Application", "Keyboard", "NavigationBar", ""):
        assert element_to_row({"class": chrome}, "ios") is None


def test_android_widget_classes_labelled_and_ambiguous_skipped():
    assert element_to_row({"class": "android.widget.EditText"}, "android")["label"] == "input"
    assert element_to_row({"class": "android.widget.CheckBox"}, "android")["label"] == "checkbox"
    assert element_to_row({"class": "androidx.appcompat.widget.AppCompatButton"}, "android")["label"] == "button"
    assert element_to_row({"class": "android.view.ViewGroup"}, "android") is None


def test_bounds_become_width_height():
    row = element_to_row({"class": "Button", "bounds": [10, 20, 110, 80]}, "ios")
    assert row["bounds"] == {"width": 100, "height": 60}


def test_extract_from_inventory_reads_screens(tmp_path):
    inv = {
        "screens": [
            {
                "platform": "ios",
                "elements": [
                    {"class": "Button", "content_desc": "home.transfer", "bounds": [0, 0, 80, 40]},
                    {"class": "Other", "bounds": [0, 0, 400, 800]},  # skipped
                    {"class": "Switch", "content_desc": "card.freeze", "bounds": [0, 0, 50, 30]},
                ],
            }
        ]
    }
    p = tmp_path / "inventory.json"
    p.write_text(json.dumps(inv), encoding="utf-8")
    rows = extract_from_inventory(p)
    assert [r["label"] for r in rows] == ["button", "switch"]


def test_build_and_load_shipped_dataset_roundtrip(tmp_path):
    d = tmp_path / "kitA"
    d.mkdir()
    (d / "inventory.json").write_text(
        json.dumps(
            {
                "screens": [
                    {
                        "platform": "ios",
                        "elements": [
                            {"class": "Button", "content_desc": "a.b", "bounds": [0, 0, 80, 40]},
                            {"class": "Switch", "content_desc": "a.c", "bounds": [0, 0, 50, 30]},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "real_elements.json"
    n = build_real_dataset([d], out=out)
    assert n == 2
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert {r["label"] for r in rows} == {"button", "switch"}
    # rows carry the feature keys the classifier's train_from_data expects
    assert "class" in rows[0] and "bounds" in rows[0] and "label" in rows[0]


def test_load_shipped_dataset_missing_is_empty(monkeypatch, tmp_path):
    import framework.ml.real_data_extractor as rde

    monkeypatch.setattr(rde, "SHIPPED_DATASET", tmp_path / "nope.json")
    assert load_shipped_real_dataset() == []


def test_extract_from_kits_dedupes_repeated_chrome(tmp_path):
    # The same tab-bar button appears in two build-type kits -> counted once.
    el = {"class": "Button", "content_desc": "tabBar.home", "text": "Home", "bounds": [0, 800, 100, 850]}
    for name in ("accessibility", "beginner"):
        d = tmp_path / name
        d.mkdir()
        (d / "inventory.json").write_text(
            json.dumps({"screens": [{"platform": "ios", "elements": [el]}]}), encoding="utf-8"
        )
    rows = extract_from_kits([tmp_path / "accessibility", tmp_path / "beginner"], dedupe=True)
    assert len(rows) == 1
    rows_dup = extract_from_kits([tmp_path / "accessibility", tmp_path / "beginner"], dedupe=False)
    assert len(rows_dup) == 2
