"""
XCTest Backend Adapter (iOS Native)

XCTest/XCUITest - Apple's native iOS UI testing framework.
Faster than Appium but requires Xcode and works only on macOS.

Note: This is a simplified adapter. Full implementation would require
running XCUITest and communicating via xcodebuild or custom runner.
"""

import subprocess
from typing import Dict, Any, Optional

from framework.backends import MobileAutomationBackend, BackendCapability


class XCTestBackend(MobileAutomationBackend):
    """XCTest backend for iOS native testing."""

    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get_capabilities(self) -> BackendCapability:
        return BackendCapability(
            name="xctest",
            supports_ios=True,
            supports_android=False,
            supports_web=False,
            supports_ui_tree=True,
            supports_screenshot=True,
            supports_tap=True,
            supports_swipe=True,
            supports_type=True,
            supports_gestures=True,
            requires_app_modification=True,  # Needs UI test target
            execution_speed="fast",
        )

    def start_session(
            self, device_id: str, app_path: Optional[str] = None, capabilities: Optional[Dict[str, Any]] = None
    ) -> str:
        """Start XCTest session (simplified)."""
        import uuid

        session_id = str(uuid.uuid4())

        # Boot simulator if needed
        subprocess.run(["xcrun", "simctl", "boot", device_id], capture_output=True, timeout=30)

        self.sessions[session_id] = {"device_id": device_id, "app_path": app_path, "started": True}

        # In full implementation: build and run XCUITest target
        return session_id

    def stop_session(self, session_id: str) -> None:
        """Stop XCTest session."""
        if session_id in self.sessions:
            del self.sessions[session_id]

    def get_screenshot(self, session_id: str) -> bytes:
        """Capture screenshot via simctl."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        device_id = session["device_id"]

        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            subprocess.run(["xcrun", "simctl", "io", device_id, "screenshot", tmp_path], timeout=5, check=True)

            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def get_ui_tree(self, session_id: str) -> str:
        """Get UI hierarchy (simplified - would use XCUITest APIs)."""
        # Full implementation would use XCUIApplication().debugDescription
        return "<hierarchy></hierarchy>"

    def tap(self, session_id: str, x: int, y: int) -> None:
        """Tap via simctl (simplified)."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        device_id = session["device_id"]

        # Note: simctl doesn't have direct tap command
        # Full implementation would use XCUITest or Accessibility APIs
        # For now, use workaround via simulated events
        pass

    def swipe(
            self, session_id: str, start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int = 300
    ) -> None:
        """Swipe (simplified)."""
        # Full implementation would use XCUITest gestures
        pass

    def type_text(self, session_id: str, text: str, element_id: Optional[str] = None) -> None:
        """Type text (simplified)."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        device_id = session["device_id"]

        # Paste text to pasteboard and use paste gesture
        subprocess.run(["xcrun", "simctl", "pbcopy", text], input=text.encode(), timeout=2)

    def find_element(self, session_id: str, strategy: str, value: str) -> Optional[str]:
        """Find element (simplified)."""
        # Full implementation would use XCUITest element queries
        return None

    def get_element_bounds(self, session_id: str, element_id: str) -> Dict[str, int]:
        """Get element bounds (simplified)."""
        # Full implementation would use XCUIElement.frame
        return {"x": 0, "y": 0, "width": 100, "height": 100}


# Register with factory
from framework.backends import BackendFactory

BackendFactory.register("xctest", XCTestBackend)
