"""TrainingDataGenerator._infer_element_type now delegates to the single canonical
rule heuristic (crawler.classify._heuristic) instead of a second, divergent copy.
These pin the resulting labels: the cases both implementations agreed on stay the
same, the divergences resolve to the *correct* answer, and the generator-specific
checkable -> checkbox mapping is preserved."""

import json

import pytest

from framework.model.app_model import ElementType
from framework.ml.training_data_generator import TrainingDataGenerator


@pytest.fixture()
def gen():
    return TrainingDataGenerator()


@pytest.mark.parametrize(
    "element,expected",
    [
        # cases both the old copy and the canonical heuristic agreed on
        ({"class": "android.widget.Button"}, ElementType.BUTTON),
        ({"class": "android.widget.ImageButton", "content_desc": "Back"}, ElementType.BUTTON),
        ({"class": "android.widget.EditText"}, ElementType.INPUT),
        ({"class": "android.widget.CheckBox", "checkable": True}, ElementType.CHECKBOX),
        ({"class": "android.widget.Switch"}, ElementType.SWITCH),
        ({"class": "android.widget.ImageView"}, ElementType.IMAGE),
        ({"class": "android.widget.TextView", "text": "Hello there"}, ElementType.TEXT),
        ({"class": "android.webkit.WebView"}, ElementType.WEBVIEW),
        ({"class": "androidx.recyclerview.widget.RecyclerView"}, ElementType.LIST),
        ({"class": "android.view.View"}, ElementType.GENERIC),
        ({"class": "android.view.View", "clickable": True, "text": "Tap"}, ElementType.BUTTON),
    ],
)
def test_infer_element_type_labels(gen, element, expected):
    assert gen._infer_element_type(element) == expected


def test_radiobutton_now_resolves_to_radio_not_button(gen):
    # The old copy checked "button" before "radio" and mislabelled this as a button;
    # the canonical heuristic gets it right.
    assert gen._infer_element_type({"class": "android.widget.RadioButton", "checkable": True}) == ElementType.RADIO


def test_bare_checkable_generic_is_a_checkbox(gen):
    # The heuristic keys checkboxes off the class name; the generator preserves the
    # checkable -> checkbox mapping for otherwise-generic controls.
    assert gen._infer_element_type({"class": "android.view.View", "checkable": True}) == ElementType.CHECKBOX


def test_auto_label_uses_the_shared_heuristic(gen):
    # auto-labelling a real hierarchy node flows through the shared heuristic, so a
    # RadioButton is tagged radio (not the old copy's mistaken "button").
    events = [{"hierarchy": {"class": "android.widget.RadioButton", "checkable": True}}]
    labelled = gen.auto_label_hierarchy_events(events)
    node = json.loads(labelled[0]["hierarchy"])
    assert node["element_type"] == ElementType.RADIO.value
