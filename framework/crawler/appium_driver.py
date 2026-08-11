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
        settle: float = 0.4,
        process_args: Optional[List[str]] = None,
    ) -> None:
        # Imported lazily so the package works without Appium installed (adb-only
        # users never pay for it, and unit tests can stub the driver).
        from appium import webdriver
        from appium.options.ios import XCUITestOptions

        self.bundle_id = bundle_id
        self._settle_max = settle
        self._cache: Optional[Tuple[float, str]] = None  # (monotonic ts, source)
        self._web: Optional[dict] = None  # active WebView snapshot (Mode 2), or None
        self._web_served = False  # have we ever served web content (gates the launch-race readiness poll)

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
        # A booted simulator is reused instead of shutting it down each run.
        options.set_capability("noReset", True)
        if process_args:
            options.set_capability("processArguments", {"args": list(process_args)})
            # processArguments only apply to a FRESH launch. With shouldTerminateApp
            # False (the reuse default), Appium attaches to an already-running app
            # and silently ignores the args — so a crawl with -SkipAuth/-DeepLink
            # stays stuck on the gate. Force a relaunch when args are supplied.
            options.set_capability("forceAppLaunch", True)
            options.set_capability("shouldTerminateApp", True)
        else:
            options.set_capability("shouldTerminateApp", False)
        # Don't block session creation waiting for the app to go quiescent — a
        # live-updating app (streaming prices) never does, so this otherwise
        # stalls every launch to its timeout.
        options.set_capability("waitForQuiescence", False)
        # WebView "Mode 2": let XCUITest surface an inspectable WKWebView as a
        # WEBVIEW_* context so the crawler can walk the DOM. The context probe is
        # only run on screens whose native tree actually contains a WebView (see
        # page_source), so this connect timeout is paid there, never on a native
        # screen. A small bound keeps that probe cheap.
        options.set_capability("webviewConnectTimeout", 2000)
        options.set_capability("ensureWebviewsHavePages", True)

        self._driver = webdriver.Remote(server, options=options)
        self._tune_for_speed()

    def _tune_for_speed(self) -> None:
        """Push WDA into its fast path. The dominant iOS cost is that XCUITest
        waits for the app to be *idle* before every command and returns a verbose,
        full-depth element snapshot — brutal on a live-updating app. These settings
        stop the idle wait, bound the snapshot, and compact the response, cutting
        per-step latency dramatically. Best-effort: an older server simply ignores
        keys it doesn't know."""
        try:
            self._driver.update_settings(
                {
                    "waitForIdleTimeout": 0,  # #1 win: never wait for "idle" (never happens on live apps)
                    "animationCoolOffTimeout": 0,
                    "shouldUseCompactResponses": True,  # smaller WDA payloads
                    "snapshotMaxDepth": 40,  # bound deep trees (ChaosBank screens are ~100+ elements)
                    "customSnapshotTimeout": 5,  # fail fast instead of hanging on a snapshot
                    "maxTypingFrequency": 60,  # type faster
                }
            )
        except Exception:
            pass

    def page_source(self) -> str:
        # Native WDA source (cheap on iOS) — from the settle cache when fresh.
        if self._cache and (time.monotonic() - self._cache[0]) < 1.0:
            native = self._cache[1]
            self._cache = None
        else:
            native = self._driver.page_source

        # WebView Mode 2: only when the native tree actually hosts a WebView do we
        # pay the context-switch probe and serve its DOM as uiautomator XML (so the
        # crawler walks the web content). Gating on the native marker keeps the
        # probe off every pure-native screen — the contexts call is not free.
        if "XCUIElementTypeWebView" in native:
            from framework.crawler import webview

            snap = webview.web_snapshot(self._driver, ready_polls=0 if self._web_served else 3)
            if snap:
                self._web = snap
                self._web_served = True
                return snap["xml"]
        self._web = None
        return native

    def _remember(self, source: str) -> None:
        self._cache = (time.monotonic(), source)

    def _settle_wait(self) -> None:
        # max_wait is deliberately below the iOS source-dump latency (~0.6s): a
        # single dump already exceeds it, so settle confirms the new screen with
        # ONE dump instead of two — halving per-gesture cost, which dominates the
        # crawl. On a fast-dump backend (adb, ~50ms) the same cap still fits two
        # dumps, so it keeps its full two-snapshot stability check there. A rare
        # mid-animation frame is recovered by _read_content_screen / _await_content.
        settle_until_stable(lambda: self._driver.page_source, self._remember, max_wait=self._settle_max)

    def tap(self, x: int, y: int) -> None:
        # In a WebView, resolve the tap to the DOM element and click it there.
        from framework.crawler import webview

        if self._web and webview.click_web(self._driver, self._web, x, y):
            self._settle_wait()
            return
        self._driver.execute_script("mobile: tap", {"x": x, "y": y})
        self._settle_wait()

    def type_text(self, text: str) -> None:
        # In a WebView, type into the focused DOM input (real key events).
        from framework.crawler import webview

        if self._web and webview.type_web(self._driver, self._web, text):
            self._settle_wait()
            return
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

    def scroll(self, direction: str = "down") -> None:
        # Reveal off-screen content. Prefer XCUITest's native `mobile: scroll`
        # (reliably scrolls the first scrollable view); fall back to a manual drag
        # for cases it can't resolve a scrollable. A screen that already fits on
        # one page simply doesn't move — harmless.
        try:
            self._driver.execute_script("mobile: scroll", {"direction": direction})
        except Exception:
            try:
                size = self._driver.get_window_size()
                x = size["width"] // 2
                lo, hi = int(size["height"] * 0.75), int(size["height"] * 0.25)
                from_y, to_y = (lo, hi) if direction == "down" else (hi, lo)
                self._driver.execute_script(
                    "mobile: dragFromToForDuration",
                    {"fromX": x, "fromY": from_y, "toX": x, "toY": to_y, "duration": 0.4},
                )
            except Exception:
                pass
        self._settle_wait()

    def refresh(self, wait: float = 0.35) -> str:
        # A second, longer look for screens whose content loads asynchronously
        # (SwiftUI `.task` / `onAppear` fetches). Those settle "stable but empty"
        # on the first read; waiting a beat and re-reading catches the real content.
        time.sleep(wait)
        self._cache = None
        page_source: str = self._driver.page_source
        return page_source

    def current_package(self) -> str:
        try:
            info = self._driver.execute_script("mobile: activeAppInfo")
            return info.get("bundleId", "") if isinstance(info, dict) else ""
        except Exception:
            return ""

    def launch(self, package: Optional[str] = None, tries: int = 8) -> bool:
        """Bring the app to the foreground and wait until it's actually there.

        Mirrors the adb driver so the crawler's recovery can re-launch a drifted or
        backgrounded iOS app (Back can't). Activates the app (launching it if not
        running), falling back to ``mobile: launchApp``, then polls activeAppInfo.
        """
        bundle = package or self.bundle_id
        try:
            self._driver.activate_app(bundle)
        except Exception:
            try:
                self._driver.execute_script("mobile: launchApp", {"bundleId": bundle})
            except Exception:
                pass
        for _ in range(tries):
            if self.current_package() == bundle:
                self._settle_wait()
                return True
            time.sleep(0.3)  # let a launch animation / splash settle
        return self.current_package() == bundle

    def quit(self) -> None:
        try:
            self._driver.quit()
        except Exception:
            pass
