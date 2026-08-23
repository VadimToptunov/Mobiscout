"""Maestro emitter: one YAML flow per case, mapping the IR onto Maestro commands and
staying honest about the selectors Maestro can't express. The emitted flows must be valid
YAML (appId header document + a command-list document)."""

import re

import yaml

from framework.codegen import get_emitter
from framework.codegen.ir import (
    ActionType,
    AssertionType,
    Platform,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)


def _emit(cases):
    model = TestModel(name="Suite", app_package="com.example.app", platform=Platform.ANDROID, cases=cases)
    return get_emitter("maestro").emit(model)


def _id(v):
    return Selector(SelectorStrategy.ID, v)


def _text(v):
    return Selector(SelectorStrategy.TEXT, v)


def _commands(flow_yaml):
    """The command-list document from a Maestro flow (the part after ---)."""
    docs = list(yaml.safe_load_all(flow_yaml))
    assert docs[0] == {"appId": "com.example.app"}  # header document
    return docs[1] or []


def test_registered_target_is_available():
    from framework.codegen import available_targets

    ids = {t.id for t in available_targets()}
    assert "maestro" in ids


def test_flow_is_valid_yaml_with_appid_header():
    files = _emit([TestCase(name="test_open", steps=[Step(action=ActionType.LAUNCH)])])
    assert list(files) == ["test_open.yaml"]
    cmds = _commands(files["test_open.yaml"])
    assert cmds == ["launchApp"] or cmds == [{"launchApp": None}] or "launchApp" in str(cmds)


def test_action_vocabulary_maps_to_maestro_commands():
    case = TestCase(
        name="test_flow",
        steps=[
            Step(action=ActionType.LAUNCH),
            Step(action=ActionType.TAP, selector=_id("com.example.app:id/go")),
            Step(action=ActionType.TYPE, selector=_text("Email"), text="a@b.com"),
            Step(action=ActionType.SWIPE, direction="up"),
            Step(action=ActionType.LONG_PRESS, selector=_id("id/item")),
            Step(action=ActionType.SCROLL_TO, selector=_text("Footer")),
            Step(action=ActionType.DEEP_LINK, text="myapp://home"),
            Step(action=ActionType.PRESS_KEY, text="enter"),
            Step(action=ActionType.BACK),
            Step(action=ActionType.WAIT, selector=_id("id/spinner"), timeout=3),
            Step(action=ActionType.ASSERT, selector=_id("id/title"), assertion=AssertionType.VISIBLE),
            Step(action=ActionType.ASSERT, selector=_id("id/err"), assertion=AssertionType.NOT_VISIBLE),
            Step(action=ActionType.ASSERT, assertion=AssertionType.TEXT_EQUALS, expected="Welcome"),
        ],
    )
    flow = _emit([case])["test_flow.yaml"]
    cmds = _commands(flow)
    verbs = [next(iter(c)) if isinstance(c, dict) else c for c in cmds]
    assert "tapOn" in verbs and "inputText" in verbs
    assert "swipe" in verbs and "longPressOn" in verbs
    assert "scrollUntilVisible" in verbs and "openLink" in verbs
    assert "pressKey" in verbs and "back" in verbs
    assert "extendedWaitUntil" in verbs
    assert verbs.count("assertVisible") == 2  # VISIBLE + TEXT_EQUALS
    assert "assertNotVisible" in verbs

    # tapOn targets the id; inputText carries the typed text; swipe carries a direction.
    tap = next(c["tapOn"] for c in cmds if isinstance(c, dict) and "tapOn" in c)
    assert tap == {"id": "com.example.app:id/go"}
    assert any(isinstance(c, dict) and c.get("inputText") == "a@b.com" for c in cmds)
    swipe = next(c["swipe"] for c in cmds if isinstance(c, dict) and "swipe" in c)
    assert swipe == {"direction": "UP"}


def test_unsupported_selector_is_skipped_not_faked():
    case = TestCase(
        name="test_xpath",
        steps=[Step(action=ActionType.TAP, selector=Selector(SelectorStrategy.XPATH, "//button[1]"))],
    )
    flow = _emit([case])["test_xpath.yaml"]
    assert "SKIPPED" in flow  # honest comment, no invented locator
    assert _commands(flow) in ([], None)  # no real command emitted for the skipped tap


def test_text_equals_asserts_on_text():
    case = TestCase(
        name="test_assert",
        steps=[Step(action=ActionType.ASSERT, assertion=AssertionType.TEXT_EQUALS, expected="Hi there")],
    )
    cmds = _commands(_emit([case])["test_assert.yaml"])
    # Text is emitted as an exact-match regex (Maestro treats text: as a regex).
    assert cmds == [{"assertVisible": {"text": re.escape("Hi there")}}]
    assert re.fullmatch(cmds[0]["assertVisible"]["text"], "Hi there")


def test_duplicate_case_names_get_distinct_files():
    files = _emit(
        [
            TestCase(name="test_dup", steps=[Step(action=ActionType.BACK)]),
            TestCase(name="test_dup", steps=[Step(action=ActionType.BACK)]),
        ]
    )
    assert set(files) == {"test_dup.yaml", "test_dup_1.yaml"}


def test_text_selectors_are_regex_escaped():
    # Maestro matches `text:` as a regex, so a literal price/label must be escaped, else
    # `4.99` matches `4X99` and `(1+)` breaks the matcher.
    case = TestCase(
        name="test_price",
        steps=[
            Step(action=ActionType.TAP, selector=_text("Buy (1+) for 4.99")),
            Step(action=ActionType.ASSERT, assertion=AssertionType.TEXT_EQUALS, expected="Total: 4.99"),
        ],
    )
    cmds = _commands(_emit([case])["test_price.yaml"])
    # After YAML decoding the value is a regex that matches the literal text exactly.
    tap_text = next(c["tapOn"]["text"] for c in cmds if isinstance(c, dict) and "tapOn" in c)
    assert tap_text == re.escape("Buy (1+) for 4.99")
    assert re.fullmatch(tap_text, "Buy (1+) for 4.99")  # matches the literal
    assert not re.fullmatch(tap_text, "BuyX(1+)Xfor 4X99")  # no longer matches a look-alike
    assert_text = next(c["assertVisible"]["text"] for c in cmds if isinstance(c, dict) and "assertVisible" in c)
    assert assert_text == re.escape("Total: 4.99")


def test_yaml_special_characters_are_escaped():
    case = TestCase(
        name="test_quote",
        steps=[Step(action=ActionType.TYPE, selector=_text('the "field"'), text='say "hi"\nbye')],
    )
    cmds = _commands(_emit([case])["test_quote.yaml"])  # must still parse
    assert any(isinstance(c, dict) and c.get("inputText") == 'say "hi"\nbye' for c in cmds)
