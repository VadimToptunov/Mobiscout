"""
Appium-backed CrawlerDriver — drives the crawler against a real iOS (or Android)
Appium session, so the same autonomous crawler that walks Android over adb can
walk an iOS app over the XCUITest driver.

The crawler only needs four things (the CrawlerDriver protocol): read the UI
tree, tap a point, go back, and name the foreground app. On iOS those map to:

    page_source()     -> driver.page_source          (XCUITest XML)
    tap(x, y)         -> mobile: tap
    back()            -> left-edge swipe (iOS has no system Back button)
    current_package() -> mobile: activeAppInfo -> bundleId

parse_screen() already understands the XCUITest XML this returns, so the rest of
the pipeline (inventory, IR, codegen) is unchanged.
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

from framework.crawler.settle import settle_until_stable


class IOSCrawlerDriver:
    """iOS CrawlerDriver: owns an Appium XCUITest session end to end."""

    def __init__(
        self,
        bundle_id: str,
        udid: Optional[str] = None,
        platform: str = "ios",
        platform_version: Optional[str] = None,
        device_name: str = "iPhone 17",
        server: str = "http://localhost:4723",
        settle: float = 1.2,
        process_args: Optional[List[str]] = None,
    ):
        # Imported lazily so the package works without Appium installed (adb-only
        # users never pay for it, and unit tests can stub the driver).
        from appium import webdriver
        from appium.options.ios import XCUITestOptions

        self.bundle_id = bundle_id
        self._settle_max = settle
        self._cache: Optional[Tuple[float, str]] = None  # (monotonic ts, source)

        options = XCUITestOptions()
        options.platform_name = "iOS"
        options.automation_name = "XCUITest"
        options.bundle_id = bundle_id
        options.device_name = device_name
        if udid:
            options.udid = udid
        if platform_version:
            options.platform_version = platform_version
        # Launch arguments passed to the app on start — how many apps reach a
        # testable state (skip onboarding/auth, deep-link a screen, enable a test
        # mode). Without them the crawl is stuck on a gate.
        if process_args:
            options.set_capability("processArguments", {"args": list(process_args)})
        # A booted simulator is reused instead of shutting it down each run.
        options.set_capability("noReset", True)
        options.set_capability("shouldTerminateApp", False)

        self._driver = webdriver.Remote(server, options=options)

    def page_source(self) -> str:
        # Serve the page source captured while settling (fresh) to avoid a second
        # WDA round-trip right after a gesture.
        if self._cache and (time.monotonic() - self._cache[0]) < 1.0:
            source = self._cache[1]
            self._cache = None
            return source
        return self._driver.page_source

    def _remember(self, source: str) -> None:
        self._cache = (time.monotonic(), source)

    def _settle_wait(self) -> None:
        settle_until_stable(lambda: self._driver.page_source, self._remember, max_wait=self._settle_max)

    def tap(self, x: int, y: int) -> None:
        self._driver.execute_script("mobile: tap", {"x": x, "y": y})
        self._settle_wait()

    def type_text(self, text: str) -> None:
        # Type into the field the previous tap focused (waypoint form-filling).
        try:
            self._driver.switch_to.active_element.send_keys(text)
        except Exception:
            pass
        self._settle_wait()

    def back(self) -> None:
        # iOS has no hardware Back; the near-universal gesture is an edge swipe
        # from the left. dragFromToForDuration works on the simulator too.
        try:
            size = self._driver.get_window_size()
            y = size["height"] // 2
            self._driver.execute_script(
                "mobile: dragFromToForDuration",
                {"fromX": 2, "fromY": y, "toX": size["width"] // 2, "toY": y, "duration": 0.3},
            )
        except Exception:
            pass
        self._settle_wait()

    def current_package(self) -> str:
        try:
            info = self._driver.execute_script("mobile: activeAppInfo")
            return info.get("bundleId", "") if isinstance(info, dict) else ""
        except Exception:
            return ""

    def quit(self) -> None:
        try:
            self._driver.quit()
        except Exception:
            pass
