"""
Device management for multi-environment test execution
STEP 2: Extended with comprehensive device layer
"""

# Legacy imports (keep for backward compatibility)
try:
    from .device_manager import DeviceManager
    from .device_pool import DevicePool
except ImportError:
    DeviceManager = None  # type: ignore[assignment]
    DevicePool = None  # type: ignore[assignment]

# STEP 2: New device layer
from .device_layer import (
    Platform,
    DeviceType,
    DeviceCapabilities,
    Device,
    LocalDeviceProvider,
    CloudDeviceProvider,
    DeviceLayer,
    Screenshot,
    LogEntry,
    APITrace,
)

__all__ = [
    # Legacy (optional for backward compatibility)
    "DeviceManager",
    "DevicePool",
    # STEP 2: Core device layer
    "Platform",
    "DeviceType",
    "DeviceCapabilities",
    "Device",
    "LocalDeviceProvider",
    "CloudDeviceProvider",
    "DeviceLayer",
    "Screenshot",
    "LogEntry",
    "APITrace",
]
