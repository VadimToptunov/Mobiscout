"""The ML classifier's class-name features are its strongest type signal. These
lock in the disambiguations that lifted synthetic accuracy from ~88% to ~95%:
WebView vs a scrollable list (both are "...View"), RadioButton vs Button
("radiobutton" contains "button"), and the scroll/collection containers that are
lists."""

import pytest

from framework.ml.element_classifier import ElementClassifier


def _flags(class_name: str) -> dict:
    """The class_* features the classifier derives from a widget class name."""
    feats = ElementClassifier().extract_features({"class": class_name})
    return {k: v for k, v in feats.items() if k.startswith("class_")}


@pytest.mark.parametrize(
    "class_name, expected_on",
    [
        ("android.webkit.WebView", "class_webview"),
        ("android.widget.RadioButton", "class_radio"),
        ("android.widget.Button", "class_button"),
        ("com.google.android.material.button.MaterialButton", "class_button"),
        ("android.widget.EditText", "class_edit"),
        ("SwiftUI.TextField", "class_edit"),
        ("android.widget.ImageView", "class_image"),
        ("android.widget.CheckBox", "class_checkbox"),
        ("android.widget.Switch", "class_switch"),
        ("androidx.recyclerview.widget.RecyclerView", "class_list"),
        ("android.widget.ScrollView", "class_list"),
        ("android.widget.GridView", "class_list"),
        ("android.widget.ExpandableListView", "class_list"),
    ],
)
def test_class_feature_fires_for_its_widget(class_name, expected_on):
    assert _flags(class_name)[expected_on] == 1.0


def test_webview_is_not_a_list():
    # The old features flagged WebView only via the noisy class_view (shared with
    # every "...View"), so it looked like a scrollable list. It must not now.
    flags = _flags("android.webkit.WebView")
    assert flags["class_webview"] == 1.0
    assert flags["class_list"] == 0.0


def test_radiobutton_is_radio_not_button():
    flags = _flags("android.widget.RadioButton")
    assert flags["class_radio"] == 1.0
    assert flags["class_button"] == 0.0


def test_recyclerview_is_list_not_bare_view():
    flags = _flags("androidx.recyclerview.widget.RecyclerView")
    assert flags["class_list"] == 1.0
    assert flags["class_view"] == 0.0  # specific view types are not the generic container


def test_plain_container_view_is_generic():
    flags = _flags("android.view.ViewGroup")
    assert flags["class_view"] == 1.0
    assert flags["class_list"] == 0.0 and flags["class_webview"] == 0.0


def test_missing_class_is_all_zero():
    flags = _flags("")
    assert set(flags.values()) == {0.0}
