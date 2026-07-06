"""
Appium-backed Android CrawlerDriver (UiAutomator2) — session-owning, like the
iOS one, so the same autonomous crawler can run over Appium instead of raw adb.

Why go through Appium for Android when adb already works? It unlocks:
  * real devices and cloud grids (BrowserStack / Sauce / LambdaTest) via caps,
  * Appium `settings` (e.g. a short idle-wait for speed),
  * a uniform driver surface with iOS.

UiAutomator2 returns the same uiautomator XML that `adb shell uiautomator dump`
produces, so parse_screen and the rest of the pipeline are unchanged.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


def build_uiautomator2_options(
    app_package: str,
    app_activity: Optional[str] = None,
    udid: Optional[str] = None,
    device_name: str = "Android Device",
    extra_caps: Optional[Dict[str, Any]] = None,
):
    """Build UiAutomator2Options (kept separate so it can be unit-tested without a
    running Appium server). extra_caps carries cloud/grid capabilities verbatim."""
    from appium.options.android import UiAutomator2Options

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.app_package = app_package
    if app_activity:
        options.app_activity = app_activity
    options.device_name = device_name
    if udid:
        options.udid = udid
    # Reuse the already-installed / running app; never wipe app data on attach.
    options.set_capability("noReset", True)
    options.set_capability("dontStopAppOnReset", True)
    for key, value in (extra_caps or {}).items():
        options.set_capability(key, value)
    return options


class AndroidAppiumDriver:
    """Owns an Appium UiAutomator2 session end to end (CrawlerDriver protocol)."""

    def __init__(
        self,
        app_package: str,
        app_activity: Optional[str] = None,
        udid: Optional[str] = None,
        device_name: str = "Android Device",
        server: str = "http://localhost:4723",
        settle: float = 0.8,
        extra_caps: Optional[Dict[str, Any]] = None,
        idle_timeout_ms: int = 100,
        _session: Any = None,
    ):
        self.app_package = app_package
        self._settle = settle
        if _session is not None:
            self._driver = _session  # injected (tests / bring-your-own session)
        else:
            from appium import webdriver

            options = build_uiautomator2_options(app_package, app_activity, udid, device_name, extra_caps)
            self._driver = webdriver.Remote(server, options=options)
        # Don't block for the full default "idle" timeout after each action — the
        # crawler settles by observing the UI itself.
        try:
            self._driver.update_settings({"waitForIdleTimeout": idle_timeout_ms})
        except Exception:
            pass

    def page_source(self) -> str:
        return self._driver.page_source

    def tap(self, x: int, y: int) -> None:
        self._driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        time.sleep(self._settle)

    def back(self) -> None:
        self._driver.back()  # Android has a real system Back
        time.sleep(self._settle)

    def current_package(self) -> str:
        try:
            return self._driver.current_package or ""
        except Exception:
            return ""

    def quit(self) -> None:
        try:
            self._driver.quit()
        except Exception:
            pass
