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
        }

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
        """Handle UI tree request."""
        session_id = params.get("session_id")

        if session_id not in self.sessions:
            raise ValueError(f"Session not found: {session_id}")

        # In production: get actual UI tree from Appium
        # For now, return mock structure
        return {
            "tree": {
                "type": "View",
                "bounds": [0, 0, 1080, 1920],
                "children": []
            }
        }

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
            "started_at": "2026-01-14T12:00:00Z"
        }

        return {
            "session_id": session_id,
            "backend": backend,
            "device_id": device_id
        }

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
                ["adb", "-s", device_id, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=5
            )

            if result.returncode == 0:
                with open(tmp_path, "wb") as f:
                    f.write(result.stdout)
            else:
                # Try iOS simulator
                subprocess.run(
                    ["xcrun", "simctl", "io", device_id, "screenshot", tmp_path],
                    check=True,
                    timeout=5
                )

            # Read and encode
            with open(tmp_path, "rb") as f:
                image_data = f.read()
                base64_data = base64.b64encode(image_data).decode('utf-8')

            # Get dimensions (simplified - just return 1080x2400 for now)
            return {
                "format": format_type,
                "data": base64_data,
                "width": 1080,
                "height": 2400
            }
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
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "tap", str(x), str(y)],
            timeout=2
        )

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
            ["adb", "-s", device_id, "shell", "input", "swipe",
             str(start_x), str(start_y), str(end_x), str(end_y), str(duration_ms)],
            timeout=2
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
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "text", escaped_text],
            timeout=2
        )

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
                "error": {
                    "code": -32600,
                    "message": "Invalid Request: jsonrpc must be '2.0'"
                }
            }

        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        # Check if method exists
        if method not in self.handlers:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

        # Execute handler
        try:
            result = self.handlers[method](params)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
        except Exception as e:
            logger.exception(f"Error handling {method}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }

    def run_stdio(self):
        """Run server using stdin/stdout."""
        logger.info("Starting JSON-RPC server (stdio mode)")

        # Send initial notification that we're ready
        ready_notification = {
            "jsonrpc": "2.0",
            "method": "notification/ready",
            "params": {
                "version": "0.5.0"
            }
        }
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
                    "error": {
                        "code": -32700,
                        "message": f"Parse error: {str(e)}"
                    }
                }
                print(json.dumps(error_response), flush=True)
            except Exception as e:
                logger.exception("Unexpected error")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                }
                print(json.dumps(error_response), flush=True)


@click.command(name="daemon")
@click.option(
    "--stdio",
    is_flag=True,
    default=True,
    help="Run in stdio mode (default)"
)
@click.option(
    "--tcp",
    type=int,
    help="Run in TCP mode on specified port (for debugging)"
)
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
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] %(levelname)s: %(message)s',
            stream=sys.stderr
        )

        try:
            server.run_stdio()
        except KeyboardInterrupt:
            logger.info("Daemon shutting down")
            sys.exit(0)
        except (OSError, ConnectionError, RuntimeError) as e:
            logger.exception("Fatal error in daemon")
            sys.exit(1)
