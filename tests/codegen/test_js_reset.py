"""The JS targets share one WebdriverIO session across a spec/feature, so — like
every other Appium target — they must reset app state before each test, or cases
leak state into each other (a "list is empty" test fails after one that adds a row).
Pins that both JS targets emit the reset and honour the MOBISCOUT_KEEP_APP_DATA
opt-out."""

import pytest

from framework.codegen.ir import ActionType, Platform, Step, TestCase, TestModel
from framework.codegen.targets import get_emitter


def _emit(target: str, platform: Platform) -> str:
    model = TestModel(
        name="Flow",
        app_package="com.example.app",
        platform=platform,
        cases=[TestCase(name="c", description="d", steps=[Step(ActionType.LAUNCH, description="Open app")])],
    )
    return "\n".join(get_emitter(target).emit(model).values())


@pytest.mark.parametrize(
    "target,hook", [("js_webdriverio", "beforeEach(resetApp)"), ("js_cucumber", "Before(resetApp)")]
)
def test_js_target_resets_app_before_each_test(target, hook):
    body = _emit(target, Platform.ANDROID)
    assert "mobile: clearApp" in body, f"{target} does not reset app data between tests"
    assert hook in body, f"{target} does not wire the reset to run before each test"
    assert "MOBISCOUT_KEEP_APP_DATA" in body, f"{target} has no opt-out of the reset"


def test_js_reset_uses_the_ios_key_on_ios():
    # XCUITest names it bundleId, not appId — the wrong key is silently ignored.
    body = _emit("js_webdriverio", Platform.IOS)
    assert "bundleId: APP_PACKAGE" in body


def test_js_webdriverio_settle_dismisses_the_soft_keyboard_on_android():
    # A raised IME (adjustResize) drops/occludes a bottom-anchored control so the next
    # assert flakes; settle() must dismiss it on Android. This is a SEMANTIC guard: the
    # golden test only checks template==golden consistency, so it can't catch this
    # dismissal being dropped (it silently was once, in a cross-branch merge).
    android = _emit("js_webdriverio", Platform.ANDROID)
    assert "isKeyboardShown()" in android and "hideKeyboard()" in android
    # Guarded to Android — iOS has no equivalent and must not emit it.
    ios = _emit("js_webdriverio", Platform.IOS)
    assert "hideKeyboard()" not in ios
