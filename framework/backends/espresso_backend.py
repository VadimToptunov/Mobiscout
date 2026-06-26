"""
Espresso Backend Adapter (Android Native)

Espresso - Google's Android UI testing framework.
Faster than Appium but requires instrumentation test APK.

Note: This is a simplified adapter. Full implementation would require
running Espresso tests and communicating via adb or custom test runner.
"""

import subprocess
from typing import Dict, Any, Optional

from framework.backends import MobileAutomationBackend, BackendCapability


class EspressoBackend(MobileAutomationBackend):
    """Espresso backend for Android native testing."""

    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get_capabilities(self) -> BackendCapability:
        return BackendCapability(
            name="espresso",
            supports_ios=False,
            supports_android=True,
            supports_web=False,
            supports_ui_tree=True,
            supports_screenshot=True,
            supports_tap=True,
            supports_swipe=True,
            supports_type=True,
            supports_gestures=True,
            requires_app_modification=True,  # Needs test APK
            execution_speed="fast"
        )

    def start_session(self, device_id: str, app_path: Optional[str] = None,
                      capabilities: Optional[Dict[str, Any]] = None) -> str:
        """Start Espresso session (simplified)."""
        import uuid
        session_id = str(uuid.uuid4())

        self.sessions[session_id] = {
            "device_id": device_id,
            "app_path": app_path,
            "started": True
        }

        # In full implementation: install test APK, start test runner
        return session_id

    def stop_session(self, session_id: str) -> None:
        """Stop Espresso session."""
        if session_id in self.sessions:
            del self.sessions[session_id]

    def get_screenshot(self, session_id: str) -> bytes:
        """Capture screenshot via adb."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        device_id = session["device_id"]

        result = subprocess.run(
            ["adb", "-s", device_id, "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=5
        )

        return result.stdout

    def get_ui_tree(self, session_id: str) -> str:
        """Get UI hierarchy via uiautomator dump."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        device_id = session["device_id"]

        # Dump UI hierarchy
        subprocess.run(
            ["adb", "-s", device_id, "shell", "uiautomator", "dump", "/sdcard/window_dump.xml"],
            timeout=5
        )

        # Pull file
        result = subprocess.run(
            ["adb", "-s", device_id, "shell", "cat", "/sdcard/window_dump.xml"],
            capture_output=True,
            text=True,
            timeout=5
        )

        return result.stdout

    def tap(self, session_id: str, x: int, y: int) -> None:
        """Tap via adb input."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        device_id = session["device_id"]
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "tap", str(x), str(y)],
            timeout=2
        )

    def swipe(self, session_id: str, start_x: int, start_y: int,
              end_x: int, end_y: int, duration_ms: int = 300) -> None:
        """Swipe via adb input."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        device_id = session["device_id"]
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "swipe",
             str(start_x), str(start_y), str(end_x), str(end_y), str(duration_ms)],
            timeout=2
        )

    def type_text(self, session_id: str, text: str, element_id: Optional[str] = None) -> None:
        """Type text via adb input."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        device_id = session["device_id"]
        escaped_text = text.replace(" ", "%s")
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "text", escaped_text],
            timeout=2
        )

    def find_element(self, session_id: str, strategy: str, value: str) -> Optional[str]:
        """Find element via UI hierarchy (simplified)."""
        # Full implementation would parse UI dump and find matching element
        return None

    def get_element_bounds(self, session_id: str, element_id: str) -> Dict[str, int]:
        """Get element bounds (simplified)."""
        # Full implementation would extract from UI hierarchy
        return {"x": 0, "y": 0, "width": 100, "height": 100}


# Register with factory
from framework.backends import BackendFactory

BackendFactory.register("espresso", EspressoBackend)
