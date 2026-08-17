"""
Per-action rendering completeness + a single keycode source of truth.

The per-action dispatch is a hand-written ``if/elif`` chain duplicated across
the imperative templates. A new :class:`ActionType` — or a branch dropped in one
target — renders to *nothing* with no error, exactly how ``SWIPE`` once silently
vanished. These tests lock the contract without a per-language expectation
table: for every imperative target and every action, a model containing the
action must emit strictly more than the same model without it. If a branch is
missing, the two outputs are equal and the test fails.

They also pin the Android keycode table to its one source
(:mod:`framework.codegen.keys`): the literal embedded in the generated BDD glue
is rendered from that table, so it can never drift from the ``keycode`` filter.
"""

from __future__ import annotations

import pytest

from framework.codegen import get_emitter, keys
from framework.codegen.emitters import _python_common
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

# Imperative targets carry the per-action dispatch (BDD glue is action-generic).
_IMPERATIVE_TARGETS = ["python_pytest", "java_testng", "kotlin_appium", "js_webdriverio"]

_SEL = Selector(SelectorStrategy.ACCESSIBILITY_ID, "el")

# LAUNCH is the baseline anchor (every model opens with it); every *other*
# action must add a visible body on top of it.
_ACTIONS = [a for a in ActionType if a is not ActionType.LAUNCH]


def _step(action: ActionType) -> Step:
    """A minimal, valid Step for each ActionType — enough for the target to
    render its body."""
    if action in (ActionType.BACK,):
        return Step(action)
    if action in (ActionType.TAP, ActionType.LONG_PRESS, ActionType.SCROLL_TO):
        return Step(action, selector=_SEL)
    if action is ActionType.TYPE:
        return Step(action, selector=_SEL, text="hello")
    if action is ActionType.SWIPE:
        return Step(action, direction="up")
    if action is ActionType.WAIT:
        return Step(action, timeout=5)
    if action is ActionType.DEEP_LINK:
        return Step(action, text="myapp://home")
    if action is ActionType.PRESS_KEY:
        return Step(action, text="ENTER")
    if action is ActionType.SWITCH_CONTEXT:
        return Step(action, text="web")
    if action is ActionType.ASSERT:
        return Step(action, selector=_SEL, assertion=AssertionType.VISIBLE)
    raise AssertionError(f"test fixture missing a Step builder for {action}")


def _emit(target_id: str, steps: list[Step], platform: Platform = Platform.ANDROID) -> str:
    model = TestModel(
        name="Coverage",
        app_package="com.example.app",
        platform=platform,
        cases=[TestCase(name="c", steps=steps)],
    )
    return "\n".join(get_emitter(target_id).emit(model).values())


@pytest.mark.parametrize("target_id", _IMPERATIVE_TARGETS)
@pytest.mark.parametrize("action", _ACTIONS, ids=lambda a: a.value)
def test_every_action_renders_a_body(target_id: str, action: ActionType):
    """No imperative target may silently drop an action: the model *with* the
    action must emit strictly more than the same model without it."""
    base = _emit(target_id, [Step(ActionType.LAUNCH)])
    with_action = _emit(target_id, [Step(ActionType.LAUNCH), _step(action)])
    assert len(with_action) > len(base), f"{target_id} renders nothing for action {action.value!r}"


def _press_key_glue(target_id: str) -> str:
    """BDD step-definition glue for a model that presses a key on Android — the
    only path that embeds the keycode literal."""
    return "\n".join(
        get_emitter(target_id)
        .emit(
            TestModel(
                name="Keys",
                app_package="com.example.app",
                platform=Platform.ANDROID,
                cases=[TestCase(name="c", steps=[Step(ActionType.PRESS_KEY, text="ENTER")])],
            )
        )
        .values()
    )


def test_keycode_table_has_one_source():
    """The literals embedded in the generated BDD glue are rendered from the
    canonical table, and the imperative filter resolves through it — so all
    three keycode consumers cannot drift apart."""
    assert keys.as_python_dict_literal() in _press_key_glue("python_pytest_bdd")
    assert keys.as_js_object_literal() in _press_key_glue("js_cucumber")
    # The imperative filter (python_pytest / js_webdriverio) agrees with the table.
    for name, code in keys.ANDROID_KEYCODES.items():
        assert _python_common.keycode(name) == code
    assert _python_common.keycode("42") == 42  # numeric passthrough
    assert _python_common.keycode("NOPE") == 0  # unknown -> no-op
