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
