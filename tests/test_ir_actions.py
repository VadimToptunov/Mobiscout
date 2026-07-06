"""New IR actions (long-press, scroll-to, deep-link, press-key) render to valid,
compiling code in the flagship python targets and to Gherkin phrases in BDD."""

import py_compile
import tempfile
from pathlib import Path

import pytest

from framework.codegen import get_emitter
from framework.codegen.emitters._bdd_common import phrase
from framework.codegen.ir import (
    ActionType,
    Platform,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)

_SEL = Selector(SelectorStrategy.ACCESSIBILITY_ID, "menu", description="Menu")
_STEPS = [
    Step(ActionType.LAUNCH),
    Step(ActionType.DEEP_LINK, text="myapp://profile"),
    Step(ActionType.LONG_PRESS, selector=_SEL),
    Step(ActionType.SCROLL_TO, selector=_SEL),
    Step(ActionType.PRESS_KEY, text="BACK"),
]


def _model(platform=Platform.ANDROID):
    return TestModel(
        name="Rich",
        app_package="com.x",
        platform=platform,
        cases=[TestCase(name="rich", steps=list(_STEPS))],
    )


def _compiles(code: str):
    p = Path(tempfile.mkdtemp()) / "gen.py"
    p.write_text(code)
    py_compile.compile(str(p), doraise=True)


@pytest.mark.parametrize("platform", [Platform.ANDROID, Platform.IOS])
def test_python_pytest_renders_and_compiles(platform):
    code = next(iter(get_emitter("python_pytest").emit(_model(platform)).values()))
    _compiles(code)
    if platform is Platform.ANDROID:
        assert "mobile: deepLink" in code
    else:
        assert 'driver.get("myapp://profile")' in code
    assert "longClickGesture" in code and "scrollIntoView" in code and "press_keycode(4)" in code


def test_bdd_steps_compile_and_feature_has_phrases():
    files = get_emitter("python_pytest_bdd").emit(_model())
    steps = next(v for k, v in files.items() if k.endswith(".py"))
    _compiles(steps)
    feature = next(v for k, v in files.items() if k.endswith(".feature"))
    for fragment in ("deep link", "long-press", "scroll to", "key"):
        assert fragment in feature


def test_phrases():
    assert phrase(Step(ActionType.DEEP_LINK, text="app://x")) == 'I open the deep link "app://x"'
    assert phrase(Step(ActionType.PRESS_KEY, text="BACK")) == 'I press the "BACK" key'
    assert phrase(Step(ActionType.LONG_PRESS, selector=_SEL)) == 'I long-press "Menu"'


def test_actiontype_roundtrips_through_dict():
    for step in _STEPS:
        assert Step.from_dict(step.to_dict()).action is step.action


@pytest.mark.parametrize(
    "target,markers",
    [
        ("js_webdriverio", ["mobile: deepLink", "longClickGesture", "scrollIntoView", "pressKeyCode"]),
        ("java_testng", ["mobile: deepLink", "clickAndHold", "androidUIAutomator", "AndroidKey.valueOf"]),
        ("kotlin_appium", ["mobile: deepLink", "clickAndHold", "androidUIAutomator", "AndroidKey.valueOf"]),
    ],
)
def test_new_actions_render_in_each_language(target, markers):
    code = "\n".join(get_emitter(target).emit(_model()).values())
    for marker in markers:
        assert marker in code, f"{target} missing {marker}"
