"""The generated kit needs the activity the app actually runs.

Found by dogfooding Omni-Notes: left unset, Appium resolves the launcher itself, and an
app declaring more than one launcher entry (its debug build ships LeakCanary, which adds
a second launcher icon) resolves to Android's chooser —
`android/com.android.internal.app.ResolverActivity` — which is not launchable. Every
generated test then errored out before it started: 8 errors, nothing ran. Reading the
activity the crawl actually ran sidesteps the ambiguity: 5 passed.
"""

from framework.crawler.adb_driver import AdbCrawlerDriver

PKG = "it.feio.android.omninotes.foss"

# Real `dumpsys activity activities | grep ResumedActivity` output shapes.
_FULLY_QUALIFIED = (
    f"    topResumedActivity=ActivityRecord{{ea8f31a u0 {PKG}/it.feio.android.omninotes.MainActivity t566}}"
)
_ABBREVIATED = "    topResumedActivity=ActivityRecord{86e5ade u0 com.example.app/.MainActivity t565}"
_OTHER_APP = "    topResumedActivity=ActivityRecord{1 u0 com.android.launcher/.Launcher t1}"


def _driver_returning(dump: str) -> AdbCrawlerDriver:
    driver = AdbCrawlerDriver(serial="test")
    driver._run = lambda *args, **kwargs: dump  # type: ignore[method-assign]
    return driver


def test_reads_the_activity_the_app_is_running():
    assert _driver_returning(_FULLY_QUALIFIED).current_activity(PKG) == "it.feio.android.omninotes.MainActivity"


def test_expands_the_dotted_shorthand_to_a_full_name():
    # dumpsys abbreviates an activity in the package's own namespace; Appium needs it whole.
    assert _driver_returning(_ABBREVIATED).current_activity("com.example.app") == "com.example.app.MainActivity"


def test_ignores_a_different_app_in_the_foreground():
    # Never hand the kit another app's activity — it would launch the wrong thing.
    assert _driver_returning(_OTHER_APP).current_activity(PKG) == ""


def test_no_resumed_activity_is_empty_not_a_guess():
    assert _driver_returning("").current_activity(PKG) == ""


# --- both platforms must start each test from a known state -------------------------
#
# Found by running the iOS kit: 7 tests, 0 passing. The crawl had started on a modal sheet
# left open by an earlier run, so it recorded that sheet as the app's entry screen and the
# generated cases asserted its contents straight after launch. Android already cleared app
# data per test; iOS cleared nothing. With the reset in place the same app went to 9 passed.

import re

from framework.codegen.ir import ActionType, Platform, Step, TestCase, TestModel
from framework.codegen.targets import get_emitter


def _model(platform: Platform, package: str) -> TestModel:
    return TestModel(
        name="Flow",
        app_package=package,
        platform=platform,
        cases=[TestCase(name="c", description="d", steps=[Step(ActionType.LAUNCH, description="Open app")])],
    )


def _emitted(platform: Platform, package: str) -> str:
    files = get_emitter("python_pytest").emit(_model(platform, package))
    return "\n".join(files.values())


def test_android_kit_clears_app_data_with_the_android_key():
    body = _emitted(Platform.ANDROID, "com.example.app")
    assert 'mobile: clearApp", {"appId": "com.example.app"}' in body


def test_ios_kit_clears_app_data_with_the_ios_key():
    # XCUITest names it bundleId, not appId — the wrong key is silently ignored, which is
    # how a kit ends up inheriting state while looking like it resets.
    body = _emitted(Platform.IOS, "com.example.App")
    assert 'mobile: clearApp", {"bundleId": "com.example.App"}' in body


def test_the_reset_can_be_opted_out_of():
    for platform in (Platform.ANDROID, Platform.IOS):
        assert re.search(r'MOBISCOUT_KEEP_APP_DATA"\)\s*!=\s*"1"', _emitted(platform, "com.example.app"))
