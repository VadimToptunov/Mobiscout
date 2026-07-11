"""Daemon command for JSON-RPC protocol server."""

import json
import logging
import subprocess
import sys
from typing import Dict, Any, Optional

import click

from framework.devices.device_manager import DeviceManager
from framework.health import HealthChecker

logger = logging.getLogger(__name__)


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

    def __init__(self):
        self.health_checker = HealthChecker()
        self.device_manager = DeviceManager()
        self.sessions = {}  # session_id -> {backend, backend_session_id, ...}
        self.backends = {}  # backend_name -> backend_instance

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
        }

    def handle_selector_generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Ranked, self-healing locator for an element — from a page source + tap
        point, or from raw element attributes. See :func:`generate_selector`."""
        return generate_selector(params)

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

    def handle_get_ui_tree(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the real UI tree for the session's device — the parsed element
        list with a semantic type per element (not a mock). Android over adb."""
        session_id = params.get("session_id")
        if session_id not in self.sessions:
            raise ValueError(f"Session not found: {session_id}")

        from framework.crawler.adb_driver import AdbCrawlerDriver

        device_id = self.sessions[session_id]["device_id"]
        source = AdbCrawlerDriver(serial=device_id).page_source()
        return ui_tree(source)

    def handle_session_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle session start request."""
        import uuid

        session_id = str(uuid.uuid4())
        device_id = params.get("device_id")
        backend = params.get("backend", "appium")

        # Store session info (actual Appium connection in Phase 3)
        self.sessions[session_id] = {
            "id": session_id,
            "device_id": device_id,
            "backend": backend,
            "started_at": "2026-01-14T12:00:00Z",
        }

        return {"session_id": session_id, "backend": backend, "device_id": device_id}

    def handle_session_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle session stop request."""
        session_id = params.get("session_id")
        if session_id in self.sessions:
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

            # Get dimensions (simplified - just return 1080x2400 for now)
            return {"format": format_type, "data": base64_data, "width": 1080, "height": 2400}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def handle_tap(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tap action."""
        session_id = params.get("session_id")
        x = params.get("x")
        y = params.get("y")

        if session_id not in self.sessions:
            raise Exception(f"Session not found: {session_id}")

        session = self.sessions[session_id]
        device_id = session["device_id"]

        # Execute tap via adb
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

    def run_stdio(self):
        """Run server using stdin/stdout."""
        logger.info("Starting JSON-RPC server (stdio mode)")

        # Send initial notification that we're ready
        ready_notification = {"jsonrpc": "2.0", "method": "notification/ready", "params": {"version": "0.5.0"}}
        print(json.dumps(ready_notification), flush=True)

        # Read requests from stdin line by line
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                response = self.handle_request(request)
                print(json.dumps(response), flush=True)
            except json.JSONDecodeError as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                }
                print(json.dumps(error_response), flush=True)
            except Exception as e:
                logger.exception("Unexpected error")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                }
                print(json.dumps(error_response), flush=True)


@click.command(name="daemon")
@click.option("--stdio", is_flag=True, default=True, help="Run in stdio mode (default)")
@click.option("--tcp", type=int, help="Run in TCP mode on specified port (for debugging)")
def daemon_command(stdio: bool, tcp: Optional[int]):
    """
    Run JSON-RPC daemon for IDE plugin communication.

    Examples:
        observe daemon --stdio
        observe daemon --tcp 33333
    """
    server = JSONRPCServer()

    if tcp:
        click.echo(f"TCP mode not yet implemented. Use --stdio for now.", err=True)
        sys.exit(1)
    else:
        # Configure logging to stderr (won't interfere with JSON-RPC on stdout)
        logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s", stream=sys.stderr)

        try:
            server.run_stdio()
        except KeyboardInterrupt:
            logger.info("Daemon shutting down")
            sys.exit(0)
        except (OSError, ConnectionError, RuntimeError) as e:
            logger.exception("Fatal error in daemon")
            sys.exit(1)
