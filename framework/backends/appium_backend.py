"""
Appium Backend Adapter

Supports:
- Appium v3.x (latest, recommended)
- Appium v2.x (backward compatible)
- Modern Selenium 4.x WebDriver API
- Plugins: images, relaxed-caps, execute-driver, etc.

STEP 7: Paid Modules Enhancement - Appium Backend Refactoring

Appium 3.x improvements:
- Enhanced driver plugins support
- Better WebDriver BiDi integration
- Improved performance and stability
- Native gesture support
"""

import json
import logging
from typing import Dict, Any, Optional

import requests
from appium import webdriver
from appium.options.common import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By

from framework.backends import MobileAutomationBackend, BackendCapability
from framework.core.exceptions import (
    BackendNotAvailableError,
    SessionError,
    SessionNotFoundError,
    ElementNotFoundError,
    DeviceConnectionError
)

logger = logging.getLogger(__name__)


class AppiumBackend(MobileAutomationBackend):
    """
    Appium backend implementation with support for Appium 2.x and 3.x.

    Features:
    - Automatic version detection
    - Plugin support (images, execute-driver, etc.)
    - Modern W3C WebDriver protocol
    - Comprehensive error handling
    - Session management

    Attributes:
        server_url: Appium server URL
        sessions: Active driver sessions
        appium_version: Detected Appium version
    """

    def __init__(self, server_url: str = "http://localhost:4723"):
        """
        Initialize Appium backend.

        Args:
            server_url: Appium server URL (default: http://localhost:4723)
        """
        self.server_url = server_url
        self.sessions: Dict[str, webdriver.Remote] = {}
        self.appium_version: Optional[str] = None

    def _detect_appium_version(self) -> Optional[str]:
        """
        Detect Appium server version.

        Returns:
            Version string or None if detection fails
        """
        try:
            # Try to get server status for version info
            response = requests.get(f"{self.server_url}/status", timeout=5)
            if response.ok:
                data = response.json()
                build_info = data.get("value", {}).get("build", {})
                version = build_info.get("version", "unknown")
                logger.info(f"Detected Appium version: {version}")
                return version
        except (requests.RequestException, json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"Could not detect Appium version: {e}")
        return None

    def get_capabilities(self) -> BackendCapability:
        """
        Get backend capabilities.

        Returns:
            BackendCapability describing supported features
        """
        return BackendCapability(
            name="appium",
            supports_ios=True,
            supports_android=True,
            supports_web=True,
            supports_ui_tree=True,
            supports_screenshot=True,
            supports_tap=True,
            supports_swipe=True,
            supports_type=True,
            supports_gestures=True,
            requires_app_modification=False,
            execution_speed="fast"  # Appium 3.x improved performance
        )

    def start_session(
            self,
            device_id: str,
            app_path: Optional[str] = None,
            capabilities: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start Appium session with auto-configuration.

        Args:
            device_id: Device UDID or emulator name
            app_path: Path to application package
            capabilities: Additional capabilities

        Returns:
            Session ID

        Raises:
            BackendNotAvailableError: If Appium server is not running
            DeviceConnectionError: If device connection fails
            SessionError: If session creation fails
        """
        caps = capabilities or {}

        # Detect Appium version on first use
        if not self.appium_version:
            self.appium_version = self._detect_appium_version()

        # Auto-detect platform
        if "emulator" in device_id.lower() or device_id.startswith("emulator-"):
            platform = "Android"
            automation_name = "UiAutomator2"
        else:
            platform = "iOS"
            automation_name = "XCUITest"

        # Build capabilities for Appium 2.x/3.x
        options = AppiumOptions()
        options.platform_name = caps.get("platformName", platform)
        options.automation_name = caps.get("automationName", automation_name)
        options.device_name = device_id
        options.udid = device_id

        if app_path:
            options.app = app_path

        # Optional capabilities
        if "noReset" in caps:
            options.no_reset = caps["noReset"]
        if "fullReset" in caps:
            options.full_reset = caps["fullReset"]

        # Appium 3.x specific optimizations
        if self.appium_version and self.appium_version.startswith("3."):
            # Enable enhanced features in Appium 3.x
            options.set_capability("appium:newCommandTimeout", 300)
            options.set_capability("appium:connectHardwareKeyboard", True)

        try:
            # Start driver
            driver = webdriver.Remote(
                command_executor=self.server_url,
                options=options
            )

            session_id = driver.session_id
            self.sessions[session_id] = driver

            logger.info(f"Started Appium session: {session_id} for device: {device_id}")
            return session_id

        except WebDriverException as e:
            if "connection refused" in str(e).lower():
                raise BackendNotAvailableError(
                    "Appium server not available",
                    details={"server_url": self.server_url, "error": str(e)}
                )
            elif "device not found" in str(e).lower():
                raise DeviceConnectionError(
                    f"Device not found: {device_id}",
                    details={"device_id": device_id, "error": str(e)}
                )
            else:
                raise SessionError(
                    f"Failed to start session: {str(e)}",
                    details={"device_id": device_id, "error": str(e)}
                )

    def stop_session(self, session_id: str) -> None:
        """
        Stop Appium session and cleanup.

        Args:
            session_id: Session ID to stop

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        if session_id not in self.sessions:
            raise SessionNotFoundError(
                f"Session not found: {session_id}",
                details={"session_id": session_id}
            )

        driver = self.sessions[session_id]
        try:
            driver.quit()
        except (WebDriverException, OSError) as e:
            logger.warning(f"Error quitting session {session_id}: {e}")
        finally:
            del self.sessions[session_id]
            logger.info(f"Stopped session: {session_id}")

    def get_screenshot(self, session_id: str) -> bytes:
        """
        Capture screenshot as PNG bytes.

        Args:
            session_id: Active session ID

        Returns:
            PNG screenshot bytes

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        driver = self.sessions.get(session_id)
        if not driver:
            raise SessionNotFoundError(
                f"Session not found: {session_id}",
                details={"session_id": session_id}
            )

        return driver.get_screenshot_as_png()

    def get_ui_tree(self, session_id: str) -> str:
        """
        Get UI hierarchy as XML.

        Args:
            session_id: Active session ID

        Returns:
            XML page source

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        driver = self.sessions.get(session_id)
        if not driver:
            raise SessionNotFoundError(
                f"Session not found: {session_id}",
                details={"session_id": session_id}
            )

        return driver.page_source

    def tap(self, session_id: str, x: int, y: int) -> None:
        """
        Tap at coordinates using W3C Actions API (Appium 2.x/3.x).

        Args:
            session_id: Active Appium session ID
            x: X coordinate
            y: Y coordinate

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        driver = self.sessions.get(session_id)
        if not driver:
            raise SessionNotFoundError(
                f"Session not found: {session_id}",
                details={"session_id": session_id}
            )

        # W3C Actions API (compatible with Appium 2.x/3.x)
        from selenium.webdriver.common.actions.action_builder import ActionBuilder
        from selenium.webdriver.common.actions.pointer_input import PointerInput
        from selenium.webdriver.common.actions import interaction

        actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "touch"))
        actions.pointer_action.move_to_location(x, y)
        actions.pointer_action.pointer_down()
        actions.pointer_action.pointer_up()
        actions.perform()

    def swipe(
            self,
            session_id: str,
            start_x: int,
            start_y: int,
            end_x: int,
            end_y: int,
            duration_ms: int = 300
    ) -> None:
        """
        Swipe gesture.

        Args:
            session_id: Active Appium session ID
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate
            duration_ms: Duration of swipe in milliseconds

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        driver = self.sessions.get(session_id)
        if not driver:
            raise SessionNotFoundError(
                f"Session not found: {session_id}",
                details={"session_id": session_id}
            )

        driver.swipe(start_x, start_y, end_x, end_y, duration_ms)

    def type_text(self, session_id: str, text: str, element_id: Optional[str] = None) -> None:
        """
        Type text into element or active field.

        Args:
            session_id: Active Appium session ID
            text: Text to type
            element_id: Optional element ID to type into

        Raises:
            SessionNotFoundError: If session doesn't exist
            ElementNotFoundError: If element_id provided but element not found
        """
        driver = self.sessions.get(session_id)
        if not driver:
            raise SessionNotFoundError(
                f"Session not found: {session_id}",
                details={"session_id": session_id}
            )

        if element_id:
            try:
                element = driver.find_element(By.ID, element_id)
                element.send_keys(text)
            except NoSuchElementException:
                raise ElementNotFoundError(
                    f"Element not found: {element_id}",
                    details={"element_id": element_id, "strategy": "id"}
                )
        else:
            # Type into active element using mobile command
            driver.execute_script("mobile: type", {"text": text})

    def find_element(self, session_id: str, strategy: str, value: str) -> Optional[str]:
        """
        Find element using modern Selenium 4.x By locators.

        Args:
            session_id: Active Appium session ID
            strategy: Locator strategy (id, xpath, accessibility_id, class_name, etc.)
            value: Locator value

        Returns:
            Element ID if found, None otherwise

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        driver = self.sessions.get(session_id)
        if not driver:
            raise SessionNotFoundError(
                f"Session not found: {session_id}",
                details={"session_id": session_id}
            )

        try:
            # Map strategy to modern By locators (Appium 2.x/3.x compatible)
            if strategy == "id":
                element = driver.find_element(By.ID, value)
            elif strategy == "xpath":
                element = driver.find_element(By.XPATH, value)
            elif strategy == "accessibility_id":
                element = driver.find_element(AppiumBy.ACCESSIBILITY_ID, value)
            elif strategy == "class_name":
                element = driver.find_element(By.CLASS_NAME, value)
            elif strategy == "name":
                element = driver.find_element(By.NAME, value)
            elif strategy == "tag_name":
                element = driver.find_element(By.TAG_NAME, value)
            elif strategy == "css_selector":
                element = driver.find_element(By.CSS_SELECTOR, value)
            # Appium-specific strategies
            elif strategy == "ios_predicate":
                element = driver.find_element(AppiumBy.IOS_PREDICATE, value)
            elif strategy == "ios_class_chain":
                element = driver.find_element(AppiumBy.IOS_CLASS_CHAIN, value)
            elif strategy == "android_uiautomator":
                element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, value)
            elif strategy == "android_viewtag":
                element = driver.find_element(AppiumBy.ANDROID_VIEWTAG, value)
            else:
                logger.warning(f"Unknown strategy: {strategy}")
                return None

            return element.id
        except NoSuchElementException:
            return None

    def get_element_bounds(self, session_id: str, element_id: str) -> Dict[str, int]:
        """
        Get element bounds (location and size).

        Args:
            session_id: Active Appium session ID
            element_id: Element identifier

        Returns:
            Dictionary with x, y, width, height

        Raises:
            SessionNotFoundError: If session doesn't exist
            ElementNotFoundError: If element not found
        """
        driver = self.sessions.get(session_id)
        if not driver:
            raise SessionNotFoundError(
                f"Session not found: {session_id}",
                details={"session_id": session_id}
            )

        try:
            # Find element using modern By.ID locator
            element = driver.find_element(By.ID, element_id)
            location = element.location
            size = element.size

            return {
                "x": location["x"],
                "y": location["y"],
                "width": size["width"],
                "height": size["height"]
            }
        except NoSuchElementException:
            raise ElementNotFoundError(
                f"Element not found: {element_id}",
                details={"element_id": element_id}
            )


# Register with factory
from framework.backends import BackendFactory

BackendFactory.register("appium", AppiumBackend)
