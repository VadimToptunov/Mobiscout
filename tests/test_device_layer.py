"""
Unit tests for STEP 2: Device Layer

Tests device management, screenshots, logs, and API tracing.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from framework.devices.device_layer import (
    Platform,
    DeviceType,
    DeviceCapabilities,
    Device,
    LocalDeviceProvider,
    CloudDeviceProvider,
    DeviceLayer,
    Screenshot,
    LogEntry,
    APITrace
)


class TestDeviceCapabilities:
    """Test DeviceCapabilities"""

    def test_create_android_capabilities(self):
        """Test Android device capabilities"""
        caps = DeviceCapabilities(
            platform=Platform.ANDROID,
            platform_version="13",
            device_name="Pixel 7",
            udid="emulator-5554",
            device_type=DeviceType.EMULATOR
        )

        assert caps.platform == Platform.ANDROID
        assert caps.platform_version == "13"
        assert caps.device_type == DeviceType.EMULATOR

    def test_create_ios_capabilities(self):
        """Test iOS device capabilities"""
        caps = DeviceCapabilities(
            platform=Platform.IOS,
            platform_version="16.0",
            device_name="iPhone 14",
            udid="12345678-1234-1234-1234-123456789012",
            device_type=DeviceType.SIMULATOR
        )

        assert caps.platform == Platform.IOS
        assert caps.device_type == DeviceType.SIMULATOR

    def test_to_appium_caps_android(self):
        """Test conversion to Appium capabilities for Android"""
        caps = DeviceCapabilities(
            platform=Platform.ANDROID,
            platform_version="13",
            device_name="Pixel 7",
            udid="emulator-5554",
            device_type=DeviceType.EMULATOR,
            app_path="/path/to/app.apk"
        )

        appium_caps = caps.to_appium_caps()

        assert appium_caps['platformName'] == "Android"
        assert appium_caps['platformVersion'] == "13"
        assert appium_caps['deviceName'] == "Pixel 7"
        assert appium_caps['app'] == "/path/to/app.apk"

    def test_to_appium_caps_ios(self):
        """Test conversion to Appium capabilities for iOS"""
        caps = DeviceCapabilities(
            platform=Platform.IOS,
            platform_version="16.0",
            device_name="iPhone 14",
            udid="12345678-1234-1234-1234-123456789012",
            device_type=DeviceType.SIMULATOR,
            app_path="/path/to/app.app"
        )

        appium_caps = caps.to_appium_caps()

        assert appium_caps['platformName'] == "Ios"
        assert appium_caps['platformVersion'] == "16.0"

    def test_extra_capabilities(self):
        """Test extra capabilities"""
        caps = DeviceCapabilities(
            platform=Platform.ANDROID,
            platform_version="13",
            device_name="Pixel 7",
            udid="emulator-5554",
            device_type=DeviceType.EMULATOR,
            extra_caps={'noReset': True, 'fullReset': False}
        )

        appium_caps = caps.to_appium_caps()

        assert appium_caps['noReset'] is True
        assert appium_caps['fullReset'] is False


class TestDevice:
    """Test Device class"""

    @pytest.fixture
    def mock_driver(self):
        """Mock Appium driver"""
        driver = Mock()
        driver.save_screenshot = Mock()
        driver.page_source = "<hierarchy>...</hierarchy>"
        driver.current_activity = "com.example.MainActivity"
        driver.get_log = Mock(return_value=[
            {'timestamp': 1234567890000, 'level': 'INFO', 'message': 'Test log'}
        ])
        return driver

    @pytest.fixture
    def device(self, mock_driver):
        """Create test device"""
        caps = DeviceCapabilities(
            platform=Platform.ANDROID,
            platform_version="13",
            device_name="Test Device",
            udid="test-123",
            device_type=DeviceType.EMULATOR
        )
        return Device(caps, mock_driver)

    def test_device_creation(self, device):
        """Test device creation"""
        assert device.platform == Platform.ANDROID
        assert device.is_connected is True
        assert len(device.screenshots) == 0
        assert len(device.logs) == 0

    def test_capture_screenshot(self, device, tmp_path):
        """Test screenshot capture"""

        # Mock save_screenshot to actually create a file
        def fake_save(path):
            Path(path).touch()

        device.driver.save_screenshot = fake_save

        screenshot = device.capture_screenshot("LoginScreen", tmp_path)

        assert screenshot.screen_name == "LoginScreen"
        assert screenshot.file_path.exists()
        assert len(device.screenshots) == 1

    def test_capture_logs(self, device):
        """Test log capture"""
        logs = device.capture_logs("logcat")

        assert len(logs) > 0
        assert len(device.logs) > 0
        assert logs[0].level == 'INFO'
        assert logs[0].message == 'Test log'

    def test_get_page_source(self, device):
        """Test getting page source"""
        source = device.get_page_source()

        assert "<hierarchy>" in source

    def test_get_current_activity(self, device):
        """Test getting current activity"""
        activity = device.get_current_activity()

        assert activity == "com.example.MainActivity"

    def test_disconnect(self, device):
        """Test device disconnect"""
        device.disconnect()

        assert device.is_connected is False
        assert device.driver.quit.called


class TestLocalDeviceProvider:
    """Test LocalDeviceProvider"""

    def test_provider_creation(self):
        """Test provider creation"""
        provider = LocalDeviceProvider()
        assert provider is not None

    @patch('subprocess.run')
    def test_list_android_devices(self, mock_run):
        """Test listing Android devices"""
        # Mock adb devices output
        mock_run.return_value = Mock(
            stdout="List of devices attached\nemulator-5554\tdevice\n",
            returncode=0
        )

        provider = LocalDeviceProvider()
        devices = provider._list_android_devices()

        # Should attempt to get device details
        assert mock_run.called

    @patch('subprocess.run')
    def test_list_ios_simulators(self, mock_run):
        """Test listing iOS simulators"""
        # Mock xcrun simctl output
        mock_run.return_value = Mock(
            stdout='{"devices": {"iOS 16.0": [{"name": "iPhone 14", "udid": "test-uuid", "isAvailable": true, "state": "Booted"}]}}',
            returncode=0
        )

        provider = LocalDeviceProvider()
        devices = provider._list_ios_simulators()

        assert mock_run.called


class TestCloudDeviceProvider:
    """Test CloudDeviceProvider"""

    @patch('framework.devices.device_layer.check_feature')
    def test_provider_creation_with_license(self, mock_check):
        """Test cloud provider creation with valid license"""
        mock_check.return_value = True

        provider = CloudDeviceProvider(
            provider='browserstack',
            username='test_user',
            access_key='test_key'
        )

        assert provider.provider == 'browserstack'
        assert provider.username == 'test_user'
        assert provider.access_key == 'test_key'

    @patch('framework.devices.device_layer.check_feature')
    def test_provider_creation_without_license(self, mock_check):
        """Test cloud provider creation without license"""
        mock_check.return_value = False

        with pytest.raises(PermissionError):
            CloudDeviceProvider(
                provider='browserstack',
                username='test_user',
                access_key='test_key'
            )

    @patch('framework.devices.device_layer.check_feature')
    def test_get_hub_url_browserstack(self, mock_check):
        """Test BrowserStack hub URL"""
        mock_check.return_value = True

        provider = CloudDeviceProvider(
            provider='browserstack',
            username='user',
            access_key='key'
        )

        assert 'browserstack.com' in provider._hub_url
        assert 'user:key' in provider._hub_url

    @patch('framework.devices.device_layer.check_feature')
    def test_get_hub_url_saucelabs(self, mock_check):
        """Test Sauce Labs hub URL"""
        mock_check.return_value = True

        provider = CloudDeviceProvider(
            provider='saucelabs',
            username='user',
            access_key='key'
        )

        assert 'saucelabs.com' in provider._hub_url

    @patch('framework.devices.device_layer.check_feature')
    def test_list_devices(self, mock_check):
        """Test listing cloud devices"""
        mock_check.return_value = True

        provider = CloudDeviceProvider(
            provider='browserstack',
            username='user',
            access_key='key'
        )

        devices = provider.list_devices()

        assert len(devices) > 0
        assert all(d.device_type == DeviceType.CLOUD for d in devices)


class TestDeviceLayer:
    """Test DeviceLayer"""

    def test_layer_creation(self):
        """Test device layer creation"""
        layer = DeviceLayer()

        assert layer.local_provider is not None
        assert layer.cloud_provider is None
        assert len(layer.connected_devices) == 0

    @patch('framework.devices.device_layer.check_feature')
    def test_configure_cloud(self, mock_check):
        """Test cloud configuration"""
        mock_check.return_value = True

        layer = DeviceLayer()
        layer.configure_cloud('browserstack', 'user', 'key')

        assert layer.cloud_provider is not None
        assert layer.cloud_provider.provider == 'browserstack'

    @patch('subprocess.run')
    def test_list_available_devices_local_only(self, mock_run):
        """Test listing local devices only"""
        mock_run.return_value = Mock(stdout="", returncode=0)

        layer = DeviceLayer()
        devices = layer.list_available_devices(include_cloud=False)

        assert isinstance(devices, list)

    @patch('framework.devices.device_layer.check_feature')
    @patch('subprocess.run')
    def test_list_available_devices_with_cloud(self, mock_run, mock_check):
        """Test listing devices including cloud"""
        mock_check.return_value = True
        mock_run.return_value = Mock(stdout="", returncode=0)

        layer = DeviceLayer()
        layer.configure_cloud('browserstack', 'user', 'key')
        devices = layer.list_available_devices(include_cloud=True)

        assert isinstance(devices, list)

    def test_connect_disconnect_device(self):
        """Test device connection and disconnection"""
        layer = DeviceLayer()

        # Mock device
        mock_driver = Mock()
        caps = DeviceCapabilities(
            platform=Platform.ANDROID,
            platform_version="13",
            device_name="Test",
            udid="test-123",
            device_type=DeviceType.EMULATOR
        )

        device = Device(caps, mock_driver)
        layer.connected_devices.append(device)

        assert len(layer.connected_devices) == 1

        layer.disconnect_device(device)

        assert len(layer.connected_devices) == 0
        assert not device.is_connected


class TestScreenshotAndLogging:
    """Test screenshot and logging features"""

    def test_screenshot_creation(self, tmp_path):
        """Test Screenshot dataclass"""
        screenshot = Screenshot(
            timestamp=datetime.now(),
            screen_name="TestScreen",
            file_path=tmp_path / "test.png"
        )

        assert screenshot.screen_name == "TestScreen"
        assert screenshot.element_id is None

    def test_log_entry_creation(self):
        """Test LogEntry dataclass"""
        log = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            message="Test message",
            source="logcat"
        )

        assert log.level == "INFO"
        assert log.message == "Test message"

    def test_api_trace_creation(self):
        """Test APITrace dataclass"""
        trace = APITrace(
            timestamp=datetime.now(),
            method="POST",
            url="https://api.example.com/login",
            request_headers={"Content-Type": "application/json"},
            request_body='{"username": "test"}',
            response_status=200,
            response_headers={"Content-Type": "application/json"},
            response_body='{"token": "abc123"}',
            duration_ms=123.45
        )

        assert trace.method == "POST"
        assert trace.response_status == 200
        assert trace.duration_ms == 123.45


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
