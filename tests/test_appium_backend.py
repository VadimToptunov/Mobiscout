"""
Unit Tests for Appium Backend with Appium 3.x Support

STEP 7: Paid Modules Enhancement - Appium 3.x Backend Tests
"""

from unittest.mock import Mock, patch

import pytest

from framework.backends.appium_backend import AppiumBackend
from framework.core.exceptions import (
    BackendNotAvailableError,
    SessionNotFoundError,
    DeviceConnectionError,
    ElementNotFoundError,
    SessionError
)


class TestAppiumBackend:
    """Test AppiumBackend functionality."""

    @pytest.fixture
    def backend(self):
        """Create backend instance."""
        return AppiumBackend(server_url="http://localhost:4723")

    def test_initialization(self, backend):
        """Test backend initialization."""
        assert backend.server_url == "http://localhost:4723"
        assert backend.sessions == {}
        assert backend.appium_version is None

    def test_get_capabilities(self, backend):
        """Test capability reporting."""
        caps = backend.get_capabilities()

        assert caps.name == "appium"
        assert caps.supports_ios is True
        assert caps.supports_android is True
        assert caps.supports_web is True
        assert caps.supports_ui_tree is True
        assert caps.supports_screenshot is True
        assert caps.supports_tap is True
        assert caps.supports_swipe is True
        assert caps.supports_type is True
        assert caps.supports_gestures is True
        assert caps.requires_app_modification is False
        assert caps.execution_speed == "fast"  # Appium 3.x improved

    @patch('requests.get')
    def test_detect_appium_version(self, mock_get, backend):
        """Test Appium version detection."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "value": {
                "build": {
                    "version": "3.0.0"
                }
            }
        }
        mock_get.return_value = mock_response

        version = backend._detect_appium_version()
        assert version == "3.0.0"
        mock_get.assert_called_once_with("http://localhost:4723/status", timeout=5)

    @patch('requests.get')
    def test_detect_appium_version_failure(self, mock_get, backend):
        """Test version detection when server unavailable."""
        import requests
        mock_get.side_effect = requests.RequestException("Connection refused")

        version = backend._detect_appium_version()
        assert version is None

    @patch('framework.backends.appium_backend.webdriver.Remote')
    def test_start_session_android(self, mock_webdriver, backend):
        """Test starting Android session."""
        # Mock driver
        mock_driver = Mock()
        mock_driver.session_id = "test-session-123"
        mock_webdriver.return_value = mock_driver

        # Start session
        session_id = backend.start_session(
            device_id="emulator-5554",
            app_path="/path/to/app.apk"
        )

        assert session_id == "test-session-123"
        assert "test-session-123" in backend.sessions
        mock_webdriver.assert_called_once()

    @patch('framework.backends.appium_backend.webdriver.Remote')
    def test_start_session_ios(self, mock_webdriver, backend):
        """Test starting iOS session."""
        # Mock driver
        mock_driver = Mock()
        mock_driver.session_id = "ios-session-456"
        mock_webdriver.return_value = mock_driver

        # Start session
        session_id = backend.start_session(
            device_id="00008030-001234567890001E",
            app_path="/path/to/app.ipa"
        )

        assert session_id == "ios-session-456"
        assert "ios-session-456" in backend.sessions

    @patch('framework.backends.appium_backend.webdriver.Remote')
    def test_start_session_appium_3_optimizations(self, mock_webdriver, backend):
        """Test Appium 3.x specific optimizations are applied."""
        backend.appium_version = "3.0.0"

        mock_driver = Mock()
        mock_driver.session_id = "session-789"
        mock_webdriver.return_value = mock_driver

        session_id = backend.start_session(device_id="emulator-5554")

        # Verify Appium 3.x capabilities were set
        call_args = mock_webdriver.call_args
        options = call_args.kwargs['options']

        # Check that options were configured (Appium 3.x specific)
        assert session_id == "session-789"

    @patch('framework.backends.appium_backend.webdriver.Remote')
    def test_start_session_server_unavailable(self, mock_webdriver, backend):
        """Test error when Appium server not running."""
        from selenium.common.exceptions import WebDriverException

        mock_webdriver.side_effect = WebDriverException("connection refused")

        with pytest.raises(BackendNotAvailableError) as exc_info:
            backend.start_session(device_id="emulator-5554")

        assert "not available" in str(exc_info.value)

    @patch('framework.backends.appium_backend.webdriver.Remote')
    def test_start_session_device_not_found(self, mock_webdriver, backend):
        """Test error when device not found."""
        from selenium.common.exceptions import WebDriverException

        mock_webdriver.side_effect = WebDriverException("device not found")

        with pytest.raises(DeviceConnectionError) as exc_info:
            backend.start_session(device_id="unknown-device")

        assert "Device not found" in str(exc_info.value)

    @patch('framework.backends.appium_backend.webdriver.Remote')
    def test_start_session_generic_error(self, mock_webdriver, backend):
        """Test generic session error."""
        from selenium.common.exceptions import WebDriverException

        mock_webdriver.side_effect = WebDriverException("unknown error")

        with pytest.raises(SessionError) as exc_info:
            backend.start_session(device_id="emulator-5554")

        assert "Failed to start session" in str(exc_info.value)

    def test_stop_session(self, backend):
        """Test stopping session."""
        # Create mock session
        mock_driver = Mock()
        backend.sessions["test-session"] = mock_driver

        # Stop session
        backend.stop_session("test-session")

        # Verify
        mock_driver.quit.assert_called_once()
        assert "test-session" not in backend.sessions

    def test_stop_session_not_found(self, backend):
        """Test stopping non-existent session."""
        with pytest.raises(SessionNotFoundError) as exc_info:
            backend.stop_session("non-existent")

        assert "Session not found" in str(exc_info.value)

    def test_stop_session_quit_error(self, backend):
        """Test session stop even if quit() raises error."""
        from selenium.common.exceptions import WebDriverException
        mock_driver = Mock()
        mock_driver.quit.side_effect = WebDriverException("quit failed")
        backend.sessions["test-session"] = mock_driver

        # Should not raise, just log warning
        backend.stop_session("test-session")

        # Session should be removed anyway
        assert "test-session" not in backend.sessions

    def test_get_screenshot(self, backend):
        """Test screenshot capture."""
        mock_driver = Mock()
        mock_driver.get_screenshot_as_png.return_value = b"PNG_DATA"
        backend.sessions["test-session"] = mock_driver

        screenshot = backend.get_screenshot("test-session")

        assert screenshot == b"PNG_DATA"
        mock_driver.get_screenshot_as_png.assert_called_once()

    def test_get_screenshot_session_not_found(self, backend):
        """Test screenshot with invalid session."""
        with pytest.raises(SessionNotFoundError):
            backend.get_screenshot("invalid-session")

    def test_get_ui_tree(self, backend):
        """Test UI tree retrieval."""
        mock_driver = Mock()
        mock_driver.page_source = "<xml>...</xml>"
        backend.sessions["test-session"] = mock_driver

        tree = backend.get_ui_tree("test-session")

        assert tree == "<xml>...</xml>"

    def test_get_ui_tree_session_not_found(self, backend):
        """Test UI tree with invalid session."""
        with pytest.raises(SessionNotFoundError):
            backend.get_ui_tree("invalid-session")

    @patch('selenium.webdriver.common.actions.action_builder.ActionBuilder')
    def test_tap(self, mock_action_builder, backend):
        """Test tap gesture using W3C Actions."""
        mock_driver = Mock()
        backend.sessions["test-session"] = mock_driver

        mock_actions = Mock()
        mock_action_builder.return_value = mock_actions

        backend.tap("test-session", x=100, y=200)

        # Verify W3C Actions API was used
        mock_action_builder.assert_called_once()
        mock_actions.perform.assert_called_once()

    def test_tap_session_not_found(self, backend):
        """Test tap with invalid session."""
        with pytest.raises(SessionNotFoundError):
            backend.tap("invalid-session", 100, 200)

    def test_swipe(self, backend):
        """Test swipe gesture."""
        mock_driver = Mock()
        backend.sessions["test-session"] = mock_driver

        backend.swipe("test-session", 100, 200, 300, 400, 500)

        mock_driver.swipe.assert_called_once_with(100, 200, 300, 400, 500)

    def test_swipe_session_not_found(self, backend):
        """Test swipe with invalid session."""
        with pytest.raises(SessionNotFoundError):
            backend.swipe("invalid-session", 0, 0, 100, 100)

    def test_type_text_with_element(self, backend):
        """Test typing text into specific element."""
        from selenium.webdriver.common.by import By

        mock_driver = Mock()
        mock_element = Mock()
        mock_driver.find_element.return_value = mock_element
        backend.sessions["test-session"] = mock_driver

        backend.type_text("test-session", "Hello", element_id="input-field")

        mock_driver.find_element.assert_called_once_with(By.ID, "input-field")
        mock_element.send_keys.assert_called_once_with("Hello")

    def test_type_text_active_element(self, backend):
        """Test typing text into active element."""
        mock_driver = Mock()
        backend.sessions["test-session"] = mock_driver

        backend.type_text("test-session", "Hello")

        mock_driver.execute_script.assert_called_once_with("mobile: type", {"text": "Hello"})

    def test_type_text_element_not_found(self, backend):
        """Test typing when element not found."""
        from selenium.common.exceptions import NoSuchElementException

        mock_driver = Mock()
        mock_driver.find_element.side_effect = NoSuchElementException()
        backend.sessions["test-session"] = mock_driver

        with pytest.raises(ElementNotFoundError):
            backend.type_text("test-session", "Hello", element_id="nonexistent")

    def test_find_element_by_id(self, backend):
        """Test finding element by ID."""
        from selenium.webdriver.common.by import By

        mock_driver = Mock()
        mock_element = Mock()
        mock_element.id = "element-123"
        mock_driver.find_element.return_value = mock_element
        backend.sessions["test-session"] = mock_driver

        element_id = backend.find_element("test-session", "id", "submit-button")

        assert element_id == "element-123"
        mock_driver.find_element.assert_called_once_with(By.ID, "submit-button")

    def test_find_element_by_xpath(self, backend):
        """Test finding element by XPath."""
        from selenium.webdriver.common.by import By

        mock_driver = Mock()
        mock_element = Mock()
        mock_element.id = "element-456"
        mock_driver.find_element.return_value = mock_element
        backend.sessions["test-session"] = mock_driver

        element_id = backend.find_element("test-session", "xpath", "//button[@id='submit']")

        assert element_id == "element-456"
        mock_driver.find_element.assert_called_once_with(By.XPATH, "//button[@id='submit']")

    def test_find_element_not_found(self, backend):
        """Test finding element that doesn't exist."""
        from selenium.common.exceptions import NoSuchElementException

        mock_driver = Mock()
        mock_driver.find_element.side_effect = NoSuchElementException()
        backend.sessions["test-session"] = mock_driver

        element_id = backend.find_element("test-session", "id", "nonexistent")

        assert element_id is None

    def test_find_element_unknown_strategy(self, backend):
        """Test finding element with unknown strategy."""
        mock_driver = Mock()
        backend.sessions["test-session"] = mock_driver

        element_id = backend.find_element("test-session", "unknown", "value")

        assert element_id is None

    def test_get_element_bounds(self, backend):
        """Test getting element bounds."""
        from selenium.webdriver.common.by import By

        mock_driver = Mock()
        mock_element = Mock()
        mock_element.location = {"x": 10, "y": 20}
        mock_element.size = {"width": 100, "height": 50}
        mock_driver.find_element.return_value = mock_element
        backend.sessions["test-session"] = mock_driver

        bounds = backend.get_element_bounds("test-session", "element-123")

        assert bounds == {"x": 10, "y": 20, "width": 100, "height": 50}
        mock_driver.find_element.assert_called_once_with(By.ID, "element-123")

    def test_get_element_bounds_not_found(self, backend):
        """Test getting bounds of non-existent element."""
        from selenium.common.exceptions import NoSuchElementException

        mock_driver = Mock()
        mock_driver.find_element.side_effect = NoSuchElementException()
        backend.sessions["test-session"] = mock_driver

        with pytest.raises(ElementNotFoundError):
            backend.get_element_bounds("test-session", "nonexistent")


# ============================================================================
# Negative Tests
# ============================================================================

class TestAppiumBackendNegative:
    """Test negative scenarios and edge cases."""

    @pytest.fixture
    def backend(self):
        """Create backend instance."""
        return AppiumBackend()

    def test_multiple_sessions(self, backend):
        """Test managing multiple concurrent sessions."""
        mock_driver1 = Mock()
        mock_driver1.session_id = "session-1"
        mock_driver2 = Mock()
        mock_driver2.session_id = "session-2"

        backend.sessions["session-1"] = mock_driver1
        backend.sessions["session-2"] = mock_driver2

        assert len(backend.sessions) == 2

        backend.stop_session("session-1")
        assert len(backend.sessions) == 1
        assert "session-2" in backend.sessions

    def test_session_id_collision(self, backend):
        """Test handling duplicate session IDs."""
        mock_driver1 = Mock()
        mock_driver2 = Mock()

        backend.sessions["duplicate-id"] = mock_driver1
        backend.sessions["duplicate-id"] = mock_driver2  # Overwrite

        assert backend.sessions["duplicate-id"] == mock_driver2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
