"""
STEP 2: Device Layer - Multi-platform Device Management

This module handles:
- Local emulators/simulators
- Real devices via USB/network
- Optional cloud devices (BrowserStack, Sauce Labs, etc.)
- Screenshot/log capture
- API trace capture
- Multi-language support
"""

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Protocol

from framework.licensing.validator import check_feature


class Platform(Enum):
    """Supported platforms"""
    ANDROID = "android"
    IOS = "ios"


class DeviceType(Enum):
    """Device types"""
    EMULATOR = "emulator"
    SIMULATOR = "simulator"
    REAL = "real"
    CLOUD = "cloud"


class DeviceStatus(Enum):
    """Device status for pool management"""
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass
class DeviceCapabilities:
    """Device capabilities"""
    platform: Platform
    platform_version: str
    device_name: str
    udid: str
    device_type: DeviceType
    automation_name: str = "Appium"
    app_path: Optional[str] = None
    browser_name: Optional[str] = None
    extra_caps: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_caps is None:
            self.extra_caps = {}

    def to_appium_caps(self) -> Dict[str, Any]:
        """Convert to Appium capabilities"""
        caps = {
            "platformName": self.platform.value.capitalize(),
            "platformVersion": self.platform_version,
            "deviceName": self.device_name,
            "udid": self.udid,
            "automationName": self.automation_name,
        }

        if self.app_path:
            caps["app"] = self.app_path

        if self.browser_name:
            caps["browserName"] = self.browser_name

        caps.update(self.extra_caps)
        return caps


@dataclass
class Screenshot:
    """Screenshot capture"""
    timestamp: datetime
    screen_name: str
    file_path: Path
    element_id: Optional[str] = None


@dataclass
class LogEntry:
    """Log entry"""
    timestamp: datetime
    level: str
    message: str
    source: str


@dataclass
class APITrace:
    """API call trace"""
    timestamp: datetime
    method: str
    url: str
    request_headers: Dict[str, str]
    request_body: Optional[str]
    response_status: int
    response_headers: Dict[str, str]
    response_body: Optional[str]
    duration_ms: float


class DeviceProvider(Protocol):
    """Protocol for device providers"""

    def list_devices(self) -> List[DeviceCapabilities]:
        """List available devices"""
        ...

    def connect(self, caps: DeviceCapabilities) -> 'Device':
        """Connect to device"""
        ...

    def disconnect(self, device: 'Device'):
        """Disconnect from device"""
        ...


class Device:
    """
    Represents a connected device/emulator/simulator

    Handles:
    - Screenshots
    - Logs
    - API traces
    - Element inspection
    """

    def __init__(self, capabilities: DeviceCapabilities, driver: Any):
        self.capabilities = capabilities
        self.driver = driver
        self.screenshots: List[Screenshot] = []
        self.logs: List[LogEntry] = []
        self.api_traces: List[APITrace] = []
        self._is_connected = True
        self.status: DeviceStatus = DeviceStatus.AVAILABLE

    @property
    def id(self) -> str:
        """Get device unique identifier"""
        return self.capabilities.udid

    @property
    def name(self) -> str:
        """Get device name"""
        return self.capabilities.device_name

    @property
    def platform(self) -> Platform:
        """Get device platform"""
        return self.capabilities.platform

    @property
    def device_id(self) -> str:
        """Get device ID (alias for id)"""
        return self.id

    @property
    def type(self) -> DeviceType:
        """Get device type"""
        return self.capabilities.device_type

    @property
    def model(self) -> str:
        """Get device model (alias for name)"""
        return self.capabilities.device_name

    @property
    def platform_version(self) -> str:
        """Get platform version"""
        return self.capabilities.platform_version

    def to_dict(self) -> Dict[str, Any]:
        """Convert device to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "device_id": self.device_id,
            "platform": self.platform.value,
            "platform_version": self.platform_version,
            "type": self.type.value,
            "model": self.model,
            "status": self.status.value,
            "is_connected": self.is_connected
        }

    @property
    def is_connected(self) -> bool:
        """Check if device is connected"""
        return self._is_connected

    def capture_screenshot(self, screen_name: str, output_dir: Path) -> Screenshot:
        """
        Capture screenshot

        Args:
            screen_name: Name of current screen
            output_dir: Directory to save screenshot

        Returns:
            Screenshot object
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now()
        filename = f"{screen_name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
        file_path = output_dir / filename

        # Capture using driver
        self.driver.save_screenshot(str(file_path))

        screenshot = Screenshot(
            timestamp=timestamp,
            screen_name=screen_name,
            file_path=file_path
        )
        self.screenshots.append(screenshot)
        return screenshot

    def capture_logs(self, log_type: str = "logcat") -> List[LogEntry]:
        """
        Capture device logs

        Args:
            log_type: Type of logs (logcat for Android, syslog for iOS)

        Returns:
            List of log entries
        """
        logs = []
        try:
            if hasattr(self.driver, 'get_log'):
                raw_logs = self.driver.get_log(log_type)
                for entry in raw_logs:
                    log = LogEntry(
                        timestamp=datetime.fromtimestamp(entry['timestamp'] / 1000),
                        level=entry.get('level', 'INFO'),
                        message=entry.get('message', ''),
                        source=log_type
                    )
                    logs.append(log)
                    self.logs.append(log)
        except (AttributeError, KeyError, TypeError) as e:
            print(f"Warning: Could not capture logs: {e}")

        return logs

    def start_api_trace(self):
        """Start capturing API traces (requires proxy or instrumentation)"""
        # This would integrate with mitmproxy or Charles Proxy
        # For now, it's a placeholder for the API tracing capability
        pass

    def stop_api_trace(self) -> List[APITrace]:
        """Stop capturing API traces"""
        return self.api_traces

    def get_page_source(self) -> str:
        """Get current page source/hierarchy"""
        return self.driver.page_source

    def get_current_activity(self) -> str:
        """Get current activity (Android) or view (iOS)"""
        if self.platform == Platform.ANDROID:
            return self.driver.current_activity
        else:
            # iOS - get current view controller
            return "iOS_View"  # Placeholder

    def disconnect(self):
        """Disconnect from device"""
        if self._is_connected:
            try:
                # Check driver is not None before accessing attributes
                if self.driver is not None and hasattr(self.driver, 'quit'):
                    self.driver.quit()
            except (OSError, RuntimeError):
                pass
            self._is_connected = False


def _validate_device_id(udid: str) -> bool:
    """
    Validate device ID format to prevent command injection.

    Valid formats:
    - Android emulator: emulator-5554
    - Android device: alphanumeric with colons (e.g., 192.168.1.1:5555)
    - iOS: UUID format (e.g., 00008101-0012345A1234001E)
    """
    import re
    # Android emulator pattern
    if re.match(r'^emulator-\d+$', udid):
        return True
    # Android device serial (alphanumeric, may include colons for network devices)
    if re.match(r'^[a-zA-Z0-9.:_-]+$', udid):
        return True
    # iOS UUID pattern
    if re.match(r'^[A-F0-9-]+$', udid, re.IGNORECASE):
        return True
    return False


class LocalDeviceProvider:
    """Provider for local emulators/simulators and real devices"""

    def list_devices(self) -> List[DeviceCapabilities]:
        """List available local devices"""
        devices = []

        # List Android devices
        devices.extend(self._list_android_devices())

        # List iOS simulators (macOS only)
        devices.extend(self._list_ios_simulators())

        return devices

    def _list_android_devices(self) -> List[DeviceCapabilities]:
        """List Android devices via adb"""
        devices = []

        try:
            result = subprocess.run(
                ['adb', 'devices', '-l'],
                capture_output=True,
                text=True,
                timeout=5
            )

            for line in result.stdout.split('\n')[1:]:
                if not line.strip() or 'List of devices' in line:
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    udid = parts[0]

                    # Validate device ID to prevent command injection
                    if not _validate_device_id(udid):
                        print(f"⚠️  Skipping device with invalid ID format: {udid}")
                        continue

                    device_type = DeviceType.EMULATOR if 'emulator' in udid else DeviceType.REAL

                    # Get device properties
                    prop_result = subprocess.run(
                        ['adb', '-s', udid, 'shell', 'getprop', 'ro.build.version.release'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    version = prop_result.stdout.strip() or "unknown"

                    name_result = subprocess.run(
                        ['adb', '-s', udid, 'shell', 'getprop', 'ro.product.model'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    name = name_result.stdout.strip() or udid

                    devices.append(DeviceCapabilities(
                        platform=Platform.ANDROID,
                        platform_version=version,
                        device_name=name,
                        udid=udid,
                        device_type=device_type,
                        automation_name="UiAutomator2"
                    ))
        except FileNotFoundError:
            print("⚠️  adb not found. Install Android SDK.")
        except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired) as e:
            print(f"⚠️  Error listing Android devices: {e}")

        return devices

    def _list_ios_simulators(self) -> List[DeviceCapabilities]:
        """List iOS simulators via xcrun simctl"""
        devices = []

        try:
            result = subprocess.run(
                ['xcrun', 'simctl', 'list', 'devices', '--json'],
                capture_output=True,
                text=True,
                timeout=5
            )

            data = json.loads(result.stdout)

            for version, device_list in data.get('devices', {}).items():
                for device in device_list:
                    if device.get('isAvailable') and device.get('state') == 'Booted':
                        # Extract iOS version from key like 'iOS 16.0'
                        ios_version = version.split()[-1] if 'iOS' in version else 'unknown'

                        devices.append(DeviceCapabilities(
                            platform=Platform.IOS,
                            platform_version=ios_version,
                            device_name=device['name'],
                            udid=device['udid'],
                            device_type=DeviceType.SIMULATOR,
                            automation_name="XCUITest"
                        ))
        except FileNotFoundError:
            # Not on macOS or Xcode not installed
            pass
        except (subprocess.SubprocessError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            print(f"⚠️  Error listing iOS simulators: {e}")

        return devices

    def connect(self, caps: DeviceCapabilities) -> Device:
        """Connect to device using Appium"""
        try:
            from appium import webdriver
            from appium.options.common import AppiumOptions
        except ImportError:
            raise ImportError("Appium client not installed. Run: pip install appium-python-client")

        # Create Appium driver using options (Appium 3.x API)
        options = AppiumOptions()
        options.load_capabilities(caps.to_appium_caps())
        driver = webdriver.Remote(
            command_executor='http://localhost:4723',
            options=options
        )

        return Device(caps, driver)

    def disconnect(self, device: Device):
        """Disconnect from device"""
        device.disconnect()


class CloudDeviceProvider:
    """
    Provider for cloud devices (BrowserStack, Sauce Labs, etc.)

    This is a PAID feature requiring PRO or ENTERPRISE license
    """

    def __init__(self, provider: str, username: str, access_key: str):
        if not check_feature('cloud_devices'):
            raise PermissionError("Cloud devices require PRO or ENTERPRISE license")

        self.provider = provider.lower()
        self.username = username
        self.access_key = access_key
        self._hub_url = self._get_hub_url()

    def _get_hub_url(self) -> str:
        """Get cloud provider hub URL"""
        urls = {
            'browserstack': f'https://{self.username}:{self.access_key}@hub-cloud.browserstack.com/wd/hub',
            'saucelabs': f'https://{self.username}:{self.access_key}@ondemand.saucelabs.com:443/wd/hub',
            'testingbot': f'https://{self.username}:{self.access_key}@hub.testingbot.com/wd/hub',
        }
        return urls.get(self.provider, '')

    def list_devices(self) -> List[DeviceCapabilities]:
        """List available cloud devices"""
        # This would query the cloud provider's API
        # For now, return common configurations
        return [
            DeviceCapabilities(
                platform=Platform.ANDROID,
                platform_version="13",
                device_name="Google Pixel 7",
                udid="cloud_pixel7",
                device_type=DeviceType.CLOUD
            ),
            DeviceCapabilities(
                platform=Platform.IOS,
                platform_version="16",
                device_name="iPhone 14",
                udid="cloud_iphone14",
                device_type=DeviceType.CLOUD
            ),
        ]

    def connect(self, caps: DeviceCapabilities) -> Device:
        """Connect to cloud device"""
        try:
            from appium import webdriver
            from appium.options.common import AppiumOptions
        except ImportError:
            raise ImportError("Appium client not installed. Run: pip install appium-python-client")

        # Create Appium driver using options (Appium 3.x API)
        options = AppiumOptions()
        options.load_capabilities(caps.to_appium_caps())
        driver = webdriver.Remote(
            command_executor=self._hub_url,
            options=options
        )

        return Device(caps, driver)

    def disconnect(self, device: Device):
        """Disconnect from cloud device"""
        device.disconnect()


class DeviceLayer:
    """
    STEP 2: Device Layer - Main interface

    Manages device connections and captures artifacts
    """

    def __init__(self):
        self.local_provider = LocalDeviceProvider()
        self.cloud_provider: Optional[CloudDeviceProvider] = None
        self.connected_devices: List[Device] = []

    def configure_cloud(self, provider: str, username: str, access_key: str):
        """Configure cloud device provider (PRO/ENTERPRISE feature)"""
        self.cloud_provider = CloudDeviceProvider(provider, username, access_key)

    def list_available_devices(self, include_cloud: bool = False) -> List[DeviceCapabilities]:
        """
        List all available devices

        Args:
            include_cloud: Include cloud devices (requires license)

        Returns:
            List of available device capabilities
        """
        devices = self.local_provider.list_devices()

        if include_cloud and self.cloud_provider:
            devices.extend(self.cloud_provider.list_devices())

        return devices

    def connect_device(self, caps: DeviceCapabilities) -> Device:
        """
        Connect to a device

        Args:
            caps: Device capabilities

        Returns:
            Connected device
        """
        if caps.device_type == DeviceType.CLOUD:
            if not self.cloud_provider:
                raise ValueError("Cloud provider not configured")
            device = self.cloud_provider.connect(caps)
        else:
            device = self.local_provider.connect(caps)

        self.connected_devices.append(device)
        return device

    def disconnect_device(self, device: Device):
        """Disconnect from device"""
        if device.capabilities.device_type == DeviceType.CLOUD:
            if self.cloud_provider:
                self.cloud_provider.disconnect(device)
        else:
            self.local_provider.disconnect(device)

        if device in self.connected_devices:
            self.connected_devices.remove(device)

    def disconnect_all(self):
        """Disconnect from all devices"""
        for device in list(self.connected_devices):
            self.disconnect_device(device)
