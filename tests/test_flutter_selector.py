"""Flutter (Route B) locator scoring (device-free).

Round-trips a synthesized Flutter widget set through the *real* parser
(:func:`build_flutter_screen` -> :func:`parse_screen` -> :func:`selector_for`),
so these tests pin the whole Route B pipeline, not a hand-built IR.

The ranking under test is **ValueKey > semantics label > text > widget type**.
It deliberately inverts the native Android order (where the accessibility label
outranks the resource-id): a Flutter ValueKey is developer-assigned and survives
copy / localisation changes, whereas a semantics label is user-facing text that
shifts with translation, so the key is the more stable locator.
"""

from framework.codegen.ir import FLUTTER_STRATEGIES, SelectorStrategy
from framework.crawler.app_crawler import parse_screen
from framework.crawler.flutter_mode import build_flutter_screen
from framework.crawler.to_codegen import selector_for


def _screen(nodes):
    xml, _ = build_flutter_screen(nodes)
    return parse_screen(xml)


def _node(i, type_, key="", label="", text="", **extra):
    base = {"i": i, "type": type_, "key": key, "label": label, "text": text, "x": 0, "y": i * 50, "w": 200, "h": 40}
    base.update(extra)
    return base


def _selector_by_type(scr, flutter_class):
    e = next(x for x in scr.elements if x.class_name == flutter_class)
    return selector_for(e, scr.elements, "android")


def test_round_trip_tags_flutter_toolkit():
    scr = _screen([_node(1, "Text", text="Hello")])
    assert scr.toolkit == "flutter"


def test_value_key_is_the_primary_locator():
    scr = _screen([_node(1, "TextField", key="email_field", label="Email", editable=True)])
    sel = _selector_by_type(scr, "FlutterTextField")
    assert sel.strategy is SelectorStrategy.FLUTTER_KEY
    assert sel.value == "email_field"
    assert sel.score == 0.95


def test_value_key_outranks_semantics_label():
    # The headline inversion vs native: a widget with BOTH a key and a semantics
    # label is located by the key, with the label demoted to a fallback.
    scr = _screen([_node(1, "ElevatedButton", key="submit_key", label="Submit", text="Submit")])
    sel = _selector_by_type(scr, "FlutterElevatedButton")
    assert sel.strategy is SelectorStrategy.FLUTTER_KEY
    assert [f.strategy for f in sel.fallbacks] == [
        SelectorStrategy.FLUTTER_SEMANTICS,
        SelectorStrategy.FLUTTER_TEXT,
        SelectorStrategy.FLUTTER_TYPE,
    ]


def test_semantics_label_outranks_text():
    # No key: the semantics label wins, the visible text is the fallback.
    scr = _screen([_node(1, "ElevatedButton", label="Log in", text="Log in")])
    sel = _selector_by_type(scr, "FlutterElevatedButton")
    assert sel.strategy is SelectorStrategy.FLUTTER_SEMANTICS
    assert sel.value == "Log in"
    assert sel.score == 0.9
    assert sel.fallbacks[0].strategy is SelectorStrategy.FLUTTER_TEXT


def test_text_outranks_bare_type():
    scr = _screen([_node(1, "Text", text="Welcome")])
    sel = _selector_by_type(scr, "FlutterText")
    assert sel.strategy is SelectorStrategy.FLUTTER_TEXT
    assert sel.value == "Welcome"
    assert sel.fallbacks[0].strategy is SelectorStrategy.FLUTTER_TYPE


def test_bare_widget_type_is_the_last_resort():
    # No key / label / text (an icon button): only the widget type remains, and it
    # is scored below the assert bar — the Flutter analogue of a positional locator.
    scr = _screen([_node(1, "IconButton")])
    sel = _selector_by_type(scr, "FlutterIconButton")
    assert sel.strategy is SelectorStrategy.FLUTTER_TYPE
    assert sel.value == "IconButton"
    assert sel.score == 0.3
    assert sel.fallbacks == []


def test_secure_text_field_type_maps_to_a_real_flutter_type():
    # A password field is synthesized as FlutterSecureTextField, but "SecureTextField"
    # is not a Flutter widget type — the type tier must use the real "TextField".
    scr = _screen([_node(1, "TextField", password=True, editable=True)])
    sel = _selector_by_type(scr, "FlutterSecureTextField")
    assert sel.strategy is SelectorStrategy.FLUTTER_TYPE
    assert sel.value == "TextField"


def test_flutter_selectors_are_a_closed_family():
    # No Flutter locator (primary or fallback) may be a native strategy: a native
    # locator would never resolve against the Flutter canvas at runtime.
    scr = _screen(
        [
            _node(1, "TextField", key="k", label="L", text="T", editable=True),
            _node(2, "ElevatedButton", label="L2", text="T2"),
            _node(3, "IconButton"),
        ]
    )
    for e in scr.elements:
        sel = selector_for(e, scr.elements, "android")
        for s in [sel, *sel.fallbacks]:
            assert s.strategy in FLUTTER_STRATEGIES, f"native strategy {s.strategy} leaked into a Flutter selector"
