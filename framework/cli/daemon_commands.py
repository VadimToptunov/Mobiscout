"""Daemon command for JSON-RPC protocol server."""

import json
import logging
import subprocess
import sys
import threading
from typing import Dict, Any, Optional

import click

from framework.devices.device_manager import DeviceManager
from framework.health import HealthChecker

logger = logging.getLogger(__name__)


def _png_dimensions(data: bytes) -> "tuple[int, int]":
    """Read (width, height) from a PNG's IHDR header.

    A PNG is an 8-byte signature followed by the IHDR chunk, whose width and
    height are two big-endian uint32s at byte offsets 16 and 20. Returns (0, 0)
    if ``data`` isn't a PNG (callers treat 0 as "unknown"), so a malformed
    capture can't raise out of the screenshot RPC.
    """
    _PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
    if len(data) < 24 or data[:8] != _PNG_SIGNATURE:
        return (0, 0)
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return (width, height)


def _format_preflight(result: Any) -> str:
    """One-line, human-readable rendering of a PreflightResult (``name: detail``,
    with the copy-pasteable fix appended when present)."""
    line = f"{result.name}: {result.detail}"
    if result.fix:
        line += f" -> {result.fix}"
    return line


def ui_tree(source: str) -> Dict[str, Any]:
    """Parse a device page source into the IDE's UI-tree response: the platform,
    toolkit and a flat element list, each with a semantic type. Pure function of
    the XML, so it's testable without a device."""
    from framework.crawler.app_crawler import parse_screen
    from framework.crawler.classify import classify

    screen = parse_screen(source)
    elements = [
        {
            "class": e.class_name,
            "resource_id": e.resource_id,
            "text": e.text,
            "content_desc": e.content_desc,
            "clickable": e.clickable,
            "bounds": list(e.bounds),
            "type": classify(e)[0],
        }
        for e in screen.elements
    ]
    return {
        "platform": screen.platform,
        "toolkit": screen.toolkit,
        "element_count": len(elements),
        "elements": elements,
    }


def generate_selector(params: Dict[str, Any]) -> Dict[str, Any]:
    """Ranked, self-healing locator for one element — the engine behind the IDE's
    "generate a locator for this element" action.

    Accepts either form:

    * ``{"source": "<page xml>", "x": .., "y": ..}`` — resolve the most specific
      element under that tap point (as the recorder does), or
    * ``{"element": {resource_id, text, content_desc, class, clickable, bounds}}``
      — build the locator straight from known attributes.

    Returns ``{found, type, label, selector}`` where ``selector`` is the ranked
    locator dict (accessibility-id → resource-id → text, with fallbacks) or None.
    Pure function — testable without a device.
    """
    from framework.crawler.app_crawler import CrawlElement, parse_screen
    from framework.crawler.classify import classify
    from framework.crawler.to_codegen import selector_for

    platform = params.get("platform", "android")

    if params.get("source") is not None and "x" in params and "y" in params:
        screen = parse_screen(params["source"])
        x, y = int(params["x"]), int(params["y"])
        siblings = screen.elements
        contained = [e for e in siblings if e.bounds[0] <= x <= e.bounds[2] and e.bounds[1] <= y <= e.bounds[3]]
        contained.sort(key=lambda e: (e.bounds[2] - e.bounds[0]) * (e.bounds[3] - e.bounds[1]))
        element = None
        for candidate in contained:  # smallest element that yields a locator wins
            if selector_for(candidate, siblings, platform) is not None:
                element = candidate
                break
        if element is None:
            element = contained[0] if contained else None
    elif params.get("element"):
        e = params["element"]
        element = CrawlElement(
            resource_id=e.get("resource_id", ""),
            text=e.get("text", ""),
            content_desc=e.get("content_desc", ""),
            class_name=e.get("class") or e.get("class_name", ""),
            clickable=bool(e.get("clickable", False)),
            bounds=tuple(e.get("bounds", (0, 0, 0, 0))),
            package=e.get("package", ""),
        )
        siblings = [element]
    else:
        raise ValueError("selector/generate requires either {source, x, y} or {element}")

    if element is None:
        return {"found": False, "type": None, "label": None, "selector": None}

    selector = selector_for(element, siblings, platform)
    return {
        "found": selector is not None,
        "type": classify(element)[0],
        "label": element.label,
        "selector": selector.to_dict() if selector else None,
    }


class JSONRPCServer:
    """JSON-RPC 2.0 server for IDE plugin communication."""

    def __init__(self) -> None:
        self.health_checker = HealthChecker()
        self.device_manager = DeviceManager()
        self.sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> {backend, backend_session_id, ...}
        self.backends: Dict[str, Any] = {}  # backend_name -> backend_instance
        # Serialize every write to the stdio transport: the log-stream pump runs on
        # a background thread and emits notifications while the main loop writes
        # responses, so their lines must not interleave.
        self._io_lock = threading.Lock()
        self._log_stream: Optional[subprocess.Popen] = None  # active `simctl log stream`

        self.handlers = {
            "health/check": self.handle_health_check,
            "device/list": self.handle_device_list,
            "backend/list": self.handle_backend_list,
            "session/start": self.handle_session_start,
            "session/stop": self.handle_session_stop,
            "ui/getScreenshot": self.handle_get_screenshot,
            "ui/getTree": self.handle_get_ui_tree,
            "action/tap": self.handle_tap,
            "action/swipe": self.handle_swipe,
            "action/type": self.handle_type,
            "kit/generate": self.handle_kit_generate,
            "codegen/generate": self.handle_kit_generate,  # alias: same parameterized pipeline
            "flow/getGraph": self.handle_flow_get_graph,
            "environment/detect": self.handle_environment_detect,
            "selector/generate": self.handle_selector_generate,
            "device/start": self.handle_device_start,
            "device/stop": self.handle_device_stop,
            "device/listAvds": self.handle_list_avds,
            "app/install": self.handle_app_install,
            "app/uninstall": self.handle_app_uninstall,
            "license/status": self.handle_license_status,
            "deeplinks/extract": self.handle_deeplinks_extract,
            "device/prepare": self.handle_device_prepare,
            "logs/start": self.handle_logs_start,
            "logs/stop": self.handle_logs_stop,
        }

    def handle_deeplinks_extract(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """The deeplinks the app declares (iOS Info.plist schemes / Android manifest
        browsable intent-filters) — the shortcuts into deep screens a tap-walk may
        miss. params: {platform, udid?, package?, source?, deeplinks?}."""
        from framework.crawler.deeplinks import extract_deeplinks

        return {"deeplinks": extract_deeplinks(params)}

    def handle_device_prepare(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Opt-in pre-crawl preset: grant the app's declared permissions and/or reset
        its state (both off unless ``grant_permissions`` / ``reset_state`` are set), so
        a system dialog can't stall a crawl. params: {platform, udid?, package?,
        source?, grant_permissions?, reset_state?}."""
        from framework.devices.prepare import prepare_device

        return prepare_device(params)

    def handle_license_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Report the active entitlement tier so the IDE can show quota and gate
        PRO-only actions. Reads ``framework.licensing`` — the open-core engine is
        UNLIMITED until a paid layer (Mobiscout-PRO) installs a limited provider,
        so this is ``pro``/unlimited on a plain engine and ``free`` with quotas
        once a FREE licence is active."""
        from framework.licensing import entitlements

        ent = entitlements()
        features = sorted(ent.features)
        return {
            "tier": ent.tier.value,
            "max_screens": ent.max_screens,
            "max_tests": ent.max_tests,
            "max_targets": ent.max_targets,
            "features": features,
            # Fully unlocked = no quota on any axis (the open-core / PRO default).
            "unlimited": ent.max_screens is None
            and ent.max_tests is None
            and ent.max_targets is None
            and ("*" in features or not features or ent.tier.value == "pro"),
        }

    def handle_selector_generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Ranked, self-healing locator for an element — from a page source + tap
        point, or from raw element attributes. See :func:`generate_selector`."""
        return generate_selector(params)

    def handle_device_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Boot an emulator/simulator so the IDE can start a session on it.

        params: {platform: "android"|"ios", target: AVD name | simulator UDID}.
        """
        platform = params.get("platform", "android")
        target = params.get("target") or params.get("avd") or params.get("udid", "")
        return self.device_manager.start_device(platform, target)

    def handle_device_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Shut down a running emulator/simulator.

        params: {platform: "android"|"ios", device_id: adb serial | simulator UDID}.
        """
        platform = params.get("platform", "android")
        device_id = params.get("device_id") or params.get("udid", "")
        return self.device_manager.stop_device(platform, device_id)

    def handle_list_avds(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List installed Android AVDs the plugin can offer to boot."""
        return {"avds": self.device_manager.list_avds()}

    def handle_app_install(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Install a build (.apk / .app) onto a device so the IDE can run a session.

        params: {platform: "android"|"ios", device_id: adb serial | simulator UDID,
                 app_path: path to the .apk/.app}. Raises if app_path is missing.
        """
        platform = params.get("platform", "android")
        device_id = params.get("device_id") or params.get("udid", "")
        app_path = params.get("app_path")
        if not app_path:
            raise ValueError("app/install requires 'app_path'")
        return self.device_manager.install_app(platform, device_id, app_path)

    def handle_app_uninstall(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Remove an installed app from a device after the IDE is done with it.

        params: {platform: "android"|"ios", device_id: adb serial | simulator UDID,
                 package: Android package | iOS bundle id}. Raises if package missing.
        """
        platform = params.get("platform", "android")
        device_id = params.get("device_id") or params.get("udid", "")
        package = params.get("package")
        if not package:
            raise ValueError("app/uninstall requires 'package'")
        return self.device_manager.uninstall_app(platform, device_id, package)

    def handle_flow_get_graph(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Crawl the app and return its interaction graph (nodes/edges + reachability,
        dead-ends, hubs) for the IDE to visualize. Same config as kit/generate."""
        from framework.crawler.pipeline import crawl_graph

        if not params.get("package"):
            raise ValueError("flow/getGraph requires 'package'")
        return crawl_graph(params)

    def handle_environment_detect(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Report the automation toolchain (Appium/drivers/SDK/Java/Xcode) with
        versions + install hints, so the IDE plugin can tell the user what to set
        up before crawling. Runs no device — safe to call anytime."""
        from framework.health.environment import detect_environment

        return detect_environment().to_dict()

    def handle_kit_generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Parameterized crawl → kit for the IDE plugin: the same config the CLI
        takes as flags, as JSON. Crawls the app described by ``params`` and writes
        the inventory, interaction graph, tests (in the chosen targets), and — if
        ``scaffold`` — a runnable project. Returns a summary of what was written.

        params: {package, platform, targets[], output, app_activity, scaffold,
                 max_steps, max_depth, serial/udid/device_name/server/extra_caps}
        """
        from framework.crawler.pipeline import run_kit

        if not params.get("package"):
            raise ValueError("kit/generate requires 'package'")
        return run_kit(params)

    def handle_health_check(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle health check request.

        Args:
            params: Request parameters (unused but required for handler interface)

        Returns:
            Health status dictionary
        """
        return self.health_checker.check()

    def handle_device_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle device list request."""
        platform = params.get("platform", "all")
        devices = self.device_manager.list_all_devices(platform)
        return {"devices": devices}

    def handle_backend_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle backend list request."""
        return {
            "backends": [
                {"name": "appium", "version": "2.x", "status": "available"},
                {"name": "uiautomator2", "version": "2.x", "status": "available"},
                {"name": "xcuitest", "version": "4.x", "status": "available"},
            ]
        }

    def _session_driver(self, session: Dict[str, Any]) -> Any:
        """The crawler driver for a session, built once and cached on it.

        Platform-aware: Android over adb, iOS over an Appium/XCUITest session — so
        the UI-tree/inspection features work on both, not just Android. Caching the
        driver keeps a repeated inspect from paying a fresh Appium/WDA connection
        every call."""
        driver = session.get("_driver")
        if driver is not None:
            return driver
        platform = str(session.get("platform") or "android").lower()
        if platform == "ios":
            from framework.crawler.appium_driver import IOSCrawlerDriver

            driver = IOSCrawlerDriver(
                bundle_id=session.get("bundle_id") or "",
                udid=session.get("device_id"),
                server=session.get("server") or "http://localhost:4723",
                process_args=session.get("launch_args"),
            )
        else:
            from framework.crawler.adb_driver import AdbCrawlerDriver

            driver = AdbCrawlerDriver(serial=session.get("device_id"))
        session["_driver"] = driver
        return driver

    def handle_get_ui_tree(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the real UI tree for the session's device — the parsed element
        list with a semantic type per element (not a mock). Works on Android (adb)
        and iOS (Appium), driven by the session's platform."""
        session_id = params.get("session_id")
        if session_id not in self.sessions:
            raise ValueError(f"Session not found: {session_id}")

        source = self._session_driver(self.sessions[session_id]).page_source()
        return ui_tree(source)

    def handle_session_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle session start request.

        Runs a fast, device-free preflight (env + Appium HTTP only — never touches
        a device) before storing the session. If any check hard-fails, raise so the
        JSON-RPC layer surfaces the actionable fix (e.g. the ANDROID_HOME message)
        to the plugin, instead of letting an Appium/UiAutomator2 session die deep
        with a cryptic error. Warn-level checks don't block — they ride along on the
        success response as ``warnings``.
        """
        import uuid

        from framework.health.preflight import ensure_android_home, preflight

        platform = params.get("platform", "android")
        backend = params.get("backend", "appium")
        server = params.get("server") or "http://localhost:4723"
        device_id = params.get("device_id")

        # Self-heal our own env first (so spawned adb inherits ANDROID_HOME), then
        # run the checks that matter for this platform/backend(=driver).
        ensure_android_home()
        results = preflight(platform, backend, server)
        failures = [r for r in results if r.level == "fail"]
        if failures:
            raise ValueError("Session preflight failed:\n" + "\n".join(_format_preflight(r) for r in failures))
        warnings = [_format_preflight(r) for r in results if r.level == "warn"]

        session_id = str(uuid.uuid4())

        # Store what building the device driver needs. The driver itself is built
        # lazily on first use (see _session_driver) so starting a session stays
        # cheap and doesn't require the device to be reachable yet.
        self.sessions[session_id] = {
            "id": session_id,
            "device_id": device_id,
            "backend": backend,
            "platform": platform,
            # iOS needs these to open an Appium session; harmless on Android.
            "bundle_id": params.get("bundle_id") or params.get("package"),
            "server": server,
            "launch_args": params.get("launch_args") or params.get("process_args"),
            "started_at": "2026-01-14T12:00:00Z",
        }

        response: Dict[str, Any] = {"session_id": session_id, "backend": backend, "device_id": device_id}
        if warnings:
            response["warnings"] = warnings
        return response

    def handle_session_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle session stop request — closing the device driver if one was
        opened (an Appium session must be quit, or it leaks on the device)."""
        session_id = str(params.get("session_id") or "")
        session = self.sessions.get(session_id)
        if session is not None:
            driver = session.get("_driver")
            if driver is not None and hasattr(driver, "quit"):
                try:
                    driver.quit()
                except Exception:
                    pass
            del self.sessions[session_id]
        return {"status": "stopped"}

    def handle_get_screenshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle screenshot capture request."""
        session_id = params.get("session_id")
        format_type = params.get("format", "png")

        if session_id not in self.sessions:
            raise Exception(f"Session not found: {session_id}")

        session = self.sessions[session_id]
        device_id = session["device_id"]

        # Capture screenshot via adb/simctl
        import subprocess
        import base64
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Try Android first
            result = subprocess.run(
                ["adb", "-s", device_id, "exec-out", "screencap", "-p"], capture_output=True, timeout=5
            )

            if result.returncode == 0:
                with open(tmp_path, "wb") as f:
                    f.write(result.stdout)
            else:
                # Try iOS simulator
                subprocess.run(["xcrun", "simctl", "io", device_id, "screenshot", tmp_path], check=True, timeout=5)

            # Read and encode
            with open(tmp_path, "rb") as f:
                image_data = f.read()
                base64_data = base64.b64encode(image_data).decode("utf-8")

            # Real dimensions from the PNG header itself — both adb `screencap -p`
            # and `simctl … screenshot` emit PNG, so this needs no extra device
            # call and works whatever the screen size (was hardcoded 1080x2400,
            # which mis-scaled coordinate taps on every other device).
            width, height = _png_dimensions(image_data)
            # Remember the mirror's pixel size so an iOS tap can map a click on it
            # back into Appium points (simctl PNG is native pixels, ~3× the points
            # `mobile: tap` expects).
            self.sessions[session_id]["_screenshot_px"] = (width, height)
            return {"format": format_type, "data": base64_data, "width": width, "height": height}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def handle_tap(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tap action.

        Platform-aware: Android taps go over adb; iOS taps go through the session's
        Appium/XCUITest driver (adb can't drive a simulator — the old adb-only path
        silently no-op'd every iOS tap). The iOS driver is built/cached lazily, so
        the first tap in a session pays the one-time WebDriverAgent build.
        """
        session_id = params.get("session_id")
        x = params.get("x")
        y = params.get("y")

        if session_id not in self.sessions:
            raise Exception(f"Session not found: {session_id}")
        if x is None or y is None:
            raise Exception("tap requires x and y coordinates")

        session = self.sessions[session_id]
        platform = str(session.get("platform") or "android").lower()

        if platform == "ios":
            driver = self._session_driver(session)
            tx, ty = int(x), int(y)
            # The Screen tab derives coordinates from the mirror, which is a native
            # simctl screenshot in pixels; `mobile: tap` wants points. Scale by the
            # pixel→point ratio so a click lands where the user aimed (skipped when
            # the caller already sent points, i.e. no screenshot was taken).
            px = session.get("_screenshot_px")
            if px and px[0] and px[1]:
                try:
                    size = driver.window_size()
                    tx = round(tx * size["width"] / px[0])
                    ty = round(ty * size["height"] / px[1])
                except Exception:
                    pass
            driver.tap(tx, ty)
        else:
            device_id = session["device_id"]
            subprocess.run(["adb", "-s", device_id, "shell", "input", "tap", str(x), str(y)], timeout=2)

        return {"status": "success", "x": x, "y": y}

    def handle_swipe(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle swipe action."""
        session_id = params.get("session_id")
        start_x = params.get("start_x")
        start_y = params.get("start_y")
        end_x = params.get("end_x")
        end_y = params.get("end_y")
        duration_ms = params.get("duration_ms", 300)

        if session_id not in self.sessions:
            raise Exception(f"Session not found: {session_id}")

        session = self.sessions[session_id]
        device_id = session["device_id"]

        # Execute swipe via adb
        subprocess.run(
            [
                "adb",
                "-s",
                device_id,
                "shell",
                "input",
                "swipe",
                str(start_x),
                str(start_y),
                str(end_x),
                str(end_y),
                str(duration_ms),
            ],
            timeout=2,
        )

        return {"status": "success"}

    def handle_type(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle type action."""
        session_id = params.get("session_id")
        text = params.get("text", "")

        if session_id not in self.sessions:
            raise Exception(f"Session not found: {session_id}")

        session = self.sessions[session_id]
        device_id = session["device_id"]

        # Execute text input via adb (escape spaces)
        escaped_text = text.replace(" ", "%s")
        subprocess.run(["adb", "-s", device_id, "shell", "input", "text", escaped_text], timeout=2)

        return {"status": "success", "text": text}

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle JSON-RPC request.

        Args:
            request: JSON-RPC request dict

        Returns:
            JSON-RPC response dict
        """
        # Validate JSON-RPC version
        if request.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32600, "message": "Invalid Request: jsonrpc must be '2.0'"},
            }

        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        # Check if method exists
        if method not in self.handlers:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        # Execute handler
        try:
            result = self.handlers[method](params)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as e:
            logger.exception(f"Error handling {method}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            }

    @staticmethod
    def _ready_notification() -> str:
        """The JSON line announcing the server is ready, sent on connect."""
        return json.dumps({"jsonrpc": "2.0", "method": "notification/ready", "params": {"version": "0.5.0"}})

    def _emit(self, obj: Dict[str, Any]) -> None:
        """Write one JSON-RPC message to stdout under the io lock. Used for
        server-initiated notifications (the log stream) so their lines never
        interleave with the main loop's responses."""
        with self._io_lock:
            sys.stdout.write(json.dumps(obj) + "\n")
            sys.stdout.flush()

    def handle_logs_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stream the app-under-test's device logs into the IDE's Logs tab.

        Platform-aware: iOS uses ``simctl spawn <udid> log stream`` filtered to the
        app process; Android uses ``adb -s <serial> logcat`` scoped to the app's PID.
        Each line is pumped back as a ``logs/message`` notification (the Logs panel
        already renders those). Replaces any stream already running.

        params: {udid | session_id, platform?, process? | bundle_id?}
        """
        udid = params.get("udid")
        bundle_id = params.get("bundle_id")
        platform = params.get("platform")
        if params.get("session_id") in self.sessions:
            session = self.sessions[params["session_id"]]
            udid = udid or session.get("device_id")
            bundle_id = bundle_id or session.get("bundle_id")
            platform = platform or session.get("platform")
        if not udid:
            raise ValueError("logs/start requires 'udid' or a live 'session_id'")
        platform = str(platform or "ios").lower()

        self._stop_log_stream()
        if platform == "android":
            # Scope logcat to the app's PID when it's running; otherwise stream the
            # whole buffer (better a noisy stream than silence). `process` overrides
            # the package used to resolve the PID.
            package = params.get("process") or bundle_id
            process = package
            cmd = ["adb", "-s", udid, "logcat", "-v", "brief"]
            pid = self._android_pid(udid, package) if package else None
            if pid:
                cmd += ["--pid", pid]
        else:
            # iOS: predicate on the app's process name; default it to the last
            # bundle-id component (e.g. com.acme.ChaosBank -> ChaosBank).
            process = params.get("process") or (str(bundle_id).rsplit(".", 1)[-1] if bundle_id else None)
            cmd = ["xcrun", "simctl", "spawn", udid, "log", "stream", "--style", "compact", "--color", "none"]
            if process:
                cmd += ["--predicate", f'process == "{process}"']
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._log_stream = proc

        def _pump(p: subprocess.Popen) -> None:
            assert p.stdout is not None
            for line in p.stdout:
                line = line.rstrip("\n")
                if line:
                    self._emit(
                        {
                            "jsonrpc": "2.0",
                            "method": "logs/message",
                            "params": {"message": line, "level": "APP", "source": "device"},
                        }
                    )

        threading.Thread(target=_pump, args=(proc,), daemon=True).start()
        return {"streaming": True, "udid": udid, "platform": platform, "process": process}

    @staticmethod
    def _android_pid(serial: str, package: str) -> Optional[str]:
        """The running PID of ``package`` on the device, or None if not running."""
        try:
            r = subprocess.run(
                ["adb", "-s", serial, "shell", "pidof", "-s", package],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return r.stdout.strip() or None
        except (subprocess.SubprocessError, OSError):
            return None

    def handle_logs_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop the app-log stream started by :meth:`handle_logs_start`."""
        self._stop_log_stream()
        return {"streaming": False}

    def _stop_log_stream(self) -> None:
        proc, self._log_stream = self._log_stream, None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _process_line(self, line: str) -> Optional[str]:
        """Handle one newline-delimited JSON-RPC request and return its response
        as a JSON string (``None`` for a blank line). Shared by the stdio and TCP
        transports so both frame and error-handle requests identically."""
        line = line.strip()
        if not line:
            return None
        try:
            request = json.loads(line)
            response = self.handle_request(request)
            return json.dumps(response)
        except json.JSONDecodeError as e:
            return json.dumps(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {str(e)}"}}
            )
        except Exception as e:
            logger.exception("Unexpected error")
            return json.dumps(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": f"Internal error: {str(e)}"}}
            )

    def run_stdio(self) -> None:
        """Run server using stdin/stdout."""
        logger.info("Starting JSON-RPC server (stdio mode)")

        with self._io_lock:
            print(self._ready_notification(), flush=True)

        for line in sys.stdin:
            response = self._process_line(line)
            if response is not None:
                # Under the io lock so a concurrent log-stream notification can't
                # interleave mid-line with this response.
                with self._io_lock:
                    print(response, flush=True)

    def run_tcp(self, port: int, host: str = "127.0.0.1") -> None:
        """Serve JSON-RPC over TCP, one client at a time — enough for the IDE
        plugin and for poking the daemon with ``nc``. Same newline-delimited JSON
        framing as stdio (via :meth:`_process_line`). Binds to localhost by
        default so the daemon is never exposed on the network."""
        import socket

        logger.info("Starting JSON-RPC server (tcp mode) on %s:%d", host, port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((host, port))
            srv.listen(1)
            while True:
                conn, addr = srv.accept()
                logger.info("Client connected: %s", addr)
                with conn, conn.makefile("rwb") as stream:
                    stream.write((self._ready_notification() + "\n").encode("utf-8"))
                    stream.flush()
                    for raw in stream:
                        response = self._process_line(raw.decode("utf-8"))
                        if response is None:
                            continue
                        stream.write((response + "\n").encode("utf-8"))
                        stream.flush()
                logger.info("Client disconnected: %s", addr)


def _activate_pro_layer() -> None:
    """Best-effort: if the paid Mobiscout-PRO package is installed, let it install
    its tiered entitlements (honouring ``MOBISCOUT_PRO_LICENSE``). A plain open-core
    engine has no such package, so this is a no-op and the engine stays UNLIMITED —
    the import/activation failure must never stop the daemon starting."""
    try:
        import mobiscout_pro  # type: ignore

        mobiscout_pro.install()
        logger.info("Mobiscout-PRO layer active")
    except Exception:
        pass  # no PRO layer (or it failed to load) — free engine runs unlimited


@click.command(name="daemon")
@click.option("--stdio", is_flag=True, default=True, help="Run in stdio mode (default)")
@click.option("--tcp", type=int, help="Run in TCP mode on specified port (for debugging)")
def daemon_command(stdio: bool, tcp: Optional[int]) -> None:
    """
    Run JSON-RPC daemon for IDE plugin communication.

    Examples:
        mobiscout daemon --stdio
        mobiscout daemon --tcp 33333
    """
    server = JSONRPCServer()
    _activate_pro_layer()

    # Log to stderr in both modes so it never corrupts the JSON-RPC stream (which
    # is stdout in stdio mode, the socket in TCP mode).
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s", stream=sys.stderr)

    try:
        if tcp:
            server.run_tcp(tcp)
        else:
            server.run_stdio()
    except KeyboardInterrupt:
        logger.info("Daemon shutting down")
        sys.exit(0)
    except (OSError, ConnectionError, RuntimeError):
        logger.exception("Fatal error in daemon")
        sys.exit(1)
