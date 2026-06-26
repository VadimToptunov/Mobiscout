"""
Configuration package for the Mobile Test Recorder framework.

Centralized configuration management with environment variable support.
"""

from .config_manager import (
    ConfigManager,
    ObserveConfig,
    FrameworkConfig,
    DeviceConfig,
    MLConfig,
    IntegrationConfig,
)
from .settings import Settings, get_settings

__all__ = [
    "Settings",
    "get_settings",
    "ConfigManager",
    "ObserveConfig",
    "FrameworkConfig",
    "DeviceConfig",
    "MLConfig",
    "IntegrationConfig",
]
