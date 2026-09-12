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
from framework.crawler.settle import settle_until_stable

# A uiautomator2 source dump normally returns in well under a second. It can hang
# indefinitely, though, when the foreground keeps the main UI thread busy so the a11y
# tree never goes idle (a lingering WebView still running JS after a hybrid handoff, an
# animation that never settles, an ANR): the server's "wait for the active window root"
# times out and retries, and — because the dump command is in flight — the whole session
# wedges (even quit() blocks). Bounding the dump lets a poisoned read surface as a driver
# error the crawler ends cleanly on, with the partial map intact, instead of hanging.
#
# The bound is generous on purpose: a *slow* dump (a heavy view tree, a busy or cold
# emulator) legitimately takes many seconds and is NOT a wedge — cutting it off early ends
# the whole crawl on a partial map for no reason (dogfooding hit exactly this at 20 s on a
# native app). Only a genuinely wedged session should exceed this, matching _HTTP_TIMEOUT_S.
_SOURCE_TIMEOUT_S = 40.0

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

# How long a frame captured while settling stays fresh enough for the crawler's
# next page_source() to reuse instead of re-dumping. The crawler asks for the source
# immediately after a gesture returns, so a wide-enough window (mirrors the iOS
# driver's 1.0s) means the adaptive settle's final dump is the one the crawler reads
# — the fixed pre-dump sleep is gone and the screen is dumped once, not twice.
_CACHE_FRESH_S = 1.0


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


def _build_client_config(server: str) -> Any:
    """A webdriver client config carrying our HTTP read timeout, or None if the
    installed client exposes no usable config class.

    Prefer Appium's own ``AppiumClientConfig``: Appium-Python-Client 6.x reads
    ``client_config.direct_connection`` inside ``webdriver.Remote`` — an attribute a
    base selenium ``ClientConfig`` doesn't have, so passing the base class raises
    ``AttributeError`` and breaks every Android-over-Appium session (real devices,
    cloud grids). The Appium subclass has it. Fall back to the base ``ClientConfig``
    for older clients, then to None (default, unbounded connection)."""
    timeout = int(_HTTP_TIMEOUT_S)
    try:
        from appium.webdriver.client_config import AppiumClientConfig

        return AppiumClientConfig(remote_server_addr=server, timeout=timeout)
    except Exception:
        pass
    try:
        from selenium.webdriver.remote.client_config import ClientConfig

        return ClientConfig(remote_server_addr=server, timeout=timeout)
    except Exception:
        return None


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
        self._cache: Optional[tuple[float, str]] = None  # (monotonic, source) from the last settle; served once
        if _session is not None:
            self._driver = _session  # injected (tests / bring-your-own session)
        else:
            from appium import webdriver

            options = build_uiautomator2_options(app_package, app_activity, udid, device_name, extra_caps)
            # Read timeout so a wedged session can't hang a command forever (see
            # _HTTP_TIMEOUT_S). Best-effort: an older client that doesn't accept
            # client_config falls back to the default (unbounded) connection.
            client_config = _build_client_config(server)
            try:
                if client_config is not None:
                    self._driver = webdriver.Remote(server, options=options, client_config=client_config)
                else:
                    self._driver = webdriver.Remote(server, options=options)
            except (TypeError, AttributeError):
                # TypeError: a client too old to accept client_config at all.
                # AttributeError: Appium-Python-Client 6.x reads .direct_connection off
                # the client_config (webdriver.py) — a base selenium ClientConfig lacks
                # it and raises. _build_client_config prefers Appium's own config to
                # avoid this; this is the last-resort fallback if that wasn't available.
                self._driver = webdriver.Remote(server, options=options)
        # Don't block for the full default "idle" timeout after each action — the
        # crawler settles by observing the UI itself.
        try:
            self._driver.update_settings({"waitForIdleTimeout": idle_timeout_ms})
        except Exception:
            pass

    def _remember(self, source: str) -> None:
        """Cache a settled frame so the crawler's next page_source() serves it instead
        of dumping again. Only non-empty frames: an empty/failed dump must fall through
        to a real read, never be served stale."""
        if source:
            self._cache = (time.monotonic(), source)

    def _settle_wait(self) -> None:
        """Wait for the UI to settle after a gesture: an adaptive poll on pure-native
        screens, the old fixed wait on WebView-capable sessions."""
        # Replace the blind post-gesture sleep with an adaptive settle on PURE-NATIVE
        # screens: poll the (bounded) uiautomator dump until the UI stops changing,
        # capped at self._settle so it is never slower than the old fixed sleep, and
        # cache the final frame for the crawler's immediate next read (dumped once,
        # not twice).
        #
        # A WebView-capable session keeps the fixed wait. Settling a WebView by native-
        # dumping it is the slow, wedge-prone path that page_source deliberately avoids
        # (it detects WebViews contexts-first, not by dumping) — so once this session
        # has ever served web content, or is on a web screen right now, don't reintroduce
        # that dump here. A wedge surfaced by the settle dump raises straight through the
        # gesture; crawl() ends on it with the partial map, exactly as a page_source wedge.
        if self._web is not None or self._web_served:
            time.sleep(self._settle)
            return
        settle_until_stable(self._native_source, self._remember, max_wait=self._settle)

    def page_source(self) -> str:
        # Serve the frame the last settle already dumped, if it is still fresh: the
        # crawler reads the source right after a gesture returns, and re-dumping the
        # just-settled screen is the redundant read this avoids. Only ever holds a
        # native frame (WebView sessions take the fixed-sleep settle path).
        if self._cache is not None and (time.monotonic() - self._cache[0]) < _CACHE_FRESH_S:
            source = self._cache[1]
            self._cache = None
            return source

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
        # A lingering hidden WebView (a web login handed off to a native screen)
        # would wedge the native uiautomator dump — web_snapshot blanks it in the
        # same context switch it already makes (neutralize_hidden), so there's no
        # extra contexts round-trip. Gated on having seen a WebView, so a pure-native
        # app never pays for it.
        snap = webview.web_snapshot(
            self._driver, ready_polls=0 if self._web_served else 2, neutralize_hidden=self._web_served
        )
        if snap:
            self._web = snap
            self._web_served = True
            return cast(str, snap["xml"])
        self._web = None
        return self._native_source()

    def _native_source(self) -> str:
        """The native uiautomator source, bounded so a WebView-poisoned dump can't
        hang the crawl. Runs the dump in a daemon thread; if it doesn't return in
        time the session is wedged (the in-flight command blocks everything after
        it, quit() included), so we flag it and raise — the crawler ends on this and
        keeps the partial map. The abandoned thread dies with the process; Appium
        reaps the orphaned session via newCommandTimeout."""
        # Once wedged, every dump is doomed and the 40s bound would be paid again on
        # each call (the settle dump, then the crawler's page_source). Fail instantly
        # after the first detection so a wedge costs one timeout, not several.
        if self._wedged:
            raise CrawlerDriverError("Appium session is wedged from an earlier hung source dump.")
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
                f"uiautomator source dump exceeded {_SOURCE_TIMEOUT_S:.0f}s — the app's UI "
                "thread stayed busy (a lingering WebView, an unsettled animation, or an ANR). "
                "For a purely native app, the adb driver avoids this entirely."
            )
        if "err" in box:
            raise CrawlerDriverError(str(box["err"]))
        return cast(str, box.get("src", ""))

    def tap(self, x: int, y: int) -> None:
        # In a WebView, resolve the tap to the DOM element and click it there.
        from framework.crawler import webview

        if self._web:
            if webview.click_web(self._driver, self._web, x, y):
                self._settle_wait()
            # A web screen's coordinates are CSS/viewport pixels, not device points
            # (see build_web_screen), so falling through to a native coordinate tap
            # here would hit an arbitrary device pixel — possibly a control the
            # crawl-safety blocklist deliberately skipped. Do nothing instead: the
            # crawler sees no navigation and moves on.
            return
        self._driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        self._settle_wait()

    def type_text(self, text: str) -> None:
        # In a WebView, type into the focused DOM input (real key events).
        from framework.crawler import webview

        if self._web and webview.type_web(self._driver, self._web, text):
            self._settle_wait()
            return
        # Type into the field the previous tap focused (waypoint form-filling /
        # input coverage). UiAutomator2 has no `mobile: type`; the reliable path is
        # send_keys to the focused element, mirroring the iOS Appium driver.
        try:
            self._driver.switch_to.active_element.send_keys(text)
        except Exception:
            pass
        self._settle_wait()

    def clear_field(self) -> None:
        # Clear the focused field so a re-fill replaces rather than appends. In a
        # WebView clear the focused DOM input; otherwise clear the active element.
        from framework.crawler import webview

        if self._web and webview.clear_web(self._driver, self._web):
            self._settle_wait()
            return
        try:
            self._driver.switch_to.active_element.clear()
        except Exception:
            pass
        self._settle_wait()

    def hide_keyboard(self) -> None:
        # Dismiss the soft keyboard after form-filling so it doesn't cover the control
        # the crawler taps next — submit sits under the IME on most forms, and the
        # crawler taps it at coordinates read before the keyboard came up. Best-effort:
        # the driver raises when no keyboard is showing.
        try:
            self._driver.hide_keyboard()
        except Exception:
            pass
        self._settle_wait()

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
        self._settle_wait()

    def refresh(self, wait: float = 1.0) -> str:
        # A second, longer look for screens whose content loads asynchronously
        # (RecyclerView population, network fetch). Those read "stable but empty" on
        # the first dump; waiting a beat and re-reading catches the real content.
        time.sleep(wait)
        return self.page_source()

    def back(self) -> None:
        self._driver.back()  # Android has a real system Back
        self._settle_wait()

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
