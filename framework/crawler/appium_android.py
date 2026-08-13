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

import threading
import time
from typing import Any, Dict, Optional, cast

from framework.crawler.errors import CrawlerDriverError

# A uiautomator2 source dump normally returns in well under a second. It can hang
# indefinitely, though, when the foreground has a WebView that keeps hogging the
# main UI thread (e.g. a hybrid app whose web login WebView lingers, still running
# JS, after handing off to a native screen): the a11y tree never goes idle, the
# server's "wait for the active window root" times out and retries, and — because
# the dump command is in flight — the whole session wedges (even quit() blocks).
# Bounding the dump lets a poisoned read surface as a driver error the crawler can
# end cleanly on, with the partial map intact, instead of hanging the run.
_SOURCE_TIMEOUT_S = 20.0

# HTTP read timeout on the Appium connection. A wedged session hangs *any* command
# in a blocking socket read (contexts, context-switch, tap — not just the source
# dump), and the read ignores Python signals, so only the client-side timeout can
# unblock it: the command raises instead of hanging forever, and the crawler ends
# on it with the partial map. Generous enough for session create + Chromedriver
# attach; only a genuinely wedged call ever reaches it.
_HTTP_TIMEOUT_S = 45.0

# One-time wait on the first read for the WEBVIEW context (Chromedriver) to attach
# after a hybrid launch — a single sleep instead of repeatedly polling contexts
# (each contexts call is itself costly while Chromedriver is spinning up).
_ATTACH_WAIT_S = 3.0


def build_uiautomator2_options(
    app_package: str,
    app_activity: Optional[str] = None,
    udid: Optional[str] = None,
    device_name: str = "Android Device",
    extra_caps: Optional[Dict[str, Any]] = None,
) -> Any:
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
    # WebView "Mode 2": make sure a debuggable WebView surfaces as a WEBVIEW_*
    # context (Chromedriver) so the crawler can walk the DOM. Needs the Appium
    # server started with `--allow-insecure chromedriver_autodownload` (or a
    # matching Chromedriver on PATH). Harmless for pure-native apps.
    options.set_capability("ensureWebviewsHavePages", True)
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
    ) -> None:
        self.app_package = app_package
        self._settle = settle
        self._web: Optional[Dict[str, Any]] = None  # active WebView snapshot (Mode 2), or None
        self._web_served = False  # have we ever served web content (gates the launch-race readiness poll)
        self._reads = 0  # page_source calls so far (the first gets the context-attach wait budget)
        self._wedged = False  # a source dump hung -> session is unusable; skip the blocking quit
        if _session is not None:
            self._driver = _session  # injected (tests / bring-your-own session)
        else:
            from appium import webdriver
            from selenium.webdriver.remote.client_config import ClientConfig

            options = build_uiautomator2_options(app_package, app_activity, udid, device_name, extra_caps)
            # Read timeout so a wedged session can't hang a command forever (see
            # _HTTP_TIMEOUT_S). Best-effort: an older client that doesn't accept
            # client_config falls back to the default (unbounded) connection.
            try:
                client_config = ClientConfig(remote_server_addr=server, timeout=_HTTP_TIMEOUT_S)
                self._driver = webdriver.Remote(server, options=options, client_config=client_config)
            except TypeError:
                self._driver = webdriver.Remote(server, options=options)
        # Don't block for the full default "idle" timeout after each action — the
        # crawler settles by observing the UI itself.
        try:
            self._driver.update_settings({"waitForIdleTimeout": idle_timeout_ms})
        except Exception:
            pass

    def page_source(self) -> str:
        # WebView Mode 2: if the current screen hosts a debuggable WebView, serve
        # its DOM as uiautomator XML so the crawler walks the web content.
        from framework.crawler import webview

        # WebView Mode 2 (contexts-first on Android: the native uiautomator dump is
        # the *slow* path on an opaque WebView, so we detect the WebView via the
        # Chromedriver context instead of dumping). The very first read waits for
        # the context to attach (Chromedriver spins up a few seconds after launch);
        # later pre-web reads only wait for the DOM to paint; post-web reads don't
        # wait at all.
        if not self._web_served and self._reads == 0:
            time.sleep(_ATTACH_WAIT_S)  # one-time: let a hybrid launch's WEBVIEW context attach
        self._reads += 1
        snap = webview.web_snapshot(self._driver, ready_polls=0 if self._web_served else 2)
        if snap:
            self._web = snap
            self._web_served = True
            return snap["xml"]
        self._web = None
        return self._native_source()

    def _native_source(self) -> str:
        """The native uiautomator source, bounded so a WebView-poisoned dump can't
        hang the crawl. Runs the dump in a daemon thread; if it doesn't return in
        time the session is wedged (the in-flight command blocks everything after
        it, quit() included), so we flag it and raise — the crawler ends on this and
        keeps the partial map. The abandoned thread dies with the process; Appium
        reaps the orphaned session via newCommandTimeout."""
        box: Dict[str, Any] = {}

        def _dump() -> None:
            try:
                box["src"] = cast(str, self._driver.page_source)
            except Exception as exc:  # noqa: BLE001 — surfaced to the caller below
                box["err"] = exc

        t = threading.Thread(target=_dump, daemon=True)
        t.start()
        t.join(_SOURCE_TIMEOUT_S)
        if t.is_alive():
            self._wedged = True
            raise CrawlerDriverError(
                f"uiautomator source dump exceeded {_SOURCE_TIMEOUT_S:.0f}s "
                "(a lingering WebView is likely hogging the UI thread)"
            )
        if "err" in box:
            raise CrawlerDriverError(str(box["err"]))
        return cast(str, box.get("src", ""))

    def tap(self, x: int, y: int) -> None:
        # In a WebView, resolve the tap to the DOM element and click it there.
        from framework.crawler import webview

        if self._web and webview.click_web(self._driver, self._web, x, y):
            time.sleep(self._settle)
            return
        self._driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        time.sleep(self._settle)

    def type_text(self, text: str) -> None:
        # In a WebView, type into the focused DOM input (real key events).
        from framework.crawler import webview

        if self._web and webview.type_web(self._driver, self._web, text):
            time.sleep(self._settle)
            return
        # Type into the field the previous tap focused (waypoint form-filling /
        # input coverage). UiAutomator2 has no `mobile: type`; the reliable path is
        # send_keys to the focused element, mirroring the iOS Appium driver.
        try:
            self._driver.switch_to.active_element.send_keys(text)
        except Exception:
            pass
        time.sleep(self._settle)

    def scroll(self, direction: str = "down") -> None:
        # Reveal off-screen content so the crawl reaches below-the-fold rows/links.
        # `mobile: scrollGesture` scrolls the largest scrollable within the given
        # rect in ``direction``; a screen that already fits doesn't move (harmless).
        try:
            size = self._driver.get_window_size()
            w, h = int(size["width"]), int(size["height"])
            self._driver.execute_script(
                "mobile: scrollGesture",
                {
                    "left": int(w * 0.1),
                    "top": int(h * 0.2),
                    "width": int(w * 0.8),
                    "height": int(h * 0.6),
                    "direction": direction,
                    "percent": 1.0,
                },
            )
        except Exception:
            pass
        time.sleep(self._settle)

    def refresh(self, wait: float = 1.0) -> str:
        # A second, longer look for screens whose content loads asynchronously
        # (RecyclerView population, network fetch). Those read "stable but empty" on
        # the first dump; waiting a beat and re-reading catches the real content.
        time.sleep(wait)
        return self.page_source()

    def back(self) -> None:
        self._driver.back()  # Android has a real system Back
        time.sleep(self._settle)

    def open_url(self, uri: str, package: Optional[str] = None, tries: int = 6) -> bool:
        """Open a deeplink URI (implicit VIEW intent) so a seed crawl starts on the
        target screen. Confirms the app under test came to the foreground when a
        ``package`` is given."""
        try:
            self._driver.get(uri)
        except Exception:
            return False
        time.sleep(self._settle)
        if package is None:
            return True
        for _ in range(tries):
            if self.current_package() == package:
                return True
            time.sleep(0.8)
        return self.current_package() == package

    def current_package(self) -> str:
        try:
            return self._driver.current_package or ""
        except Exception:
            return ""

    def quit(self) -> None:
        # A wedged session blocks quit() too (the hung dump is still in flight), so
        # fire it off best-effort and don't wait — the server reaps the session.
        if self._wedged:
            threading.Thread(target=self._safe_quit, daemon=True).start()
            return
        self._safe_quit()

    def _safe_quit(self) -> None:
        try:
            self._driver.quit()
        except Exception:
            pass
