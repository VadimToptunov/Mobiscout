"""
Configuration Management System

Centralized configuration management with YAML/JSON support,
environment variables, profiles, and validation.
"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml

try:
    from yaml import CSafeLoader as SafeLoader, CDumper as Dumper
except ImportError:
    from yaml import SafeLoader, Dumper

from pydantic import BaseModel, Field


class FrameworkConfig(BaseModel):
    """Framework-level configuration"""
    timeout: int = Field(default=30, description="Default timeout in seconds")
    retry_count: int = Field(default=3, description="Number of retries")
    log_level: str = Field(default="INFO", description="Logging level")
    implicit_wait: int = Field(default=10, description="Implicit wait in seconds")
    screenshot_on_failure: bool = Field(default=True)
    video_recording: bool = Field(default=False)


class DeviceConfig(BaseModel):
    """Device-specific configuration"""

    class AndroidConfig(BaseModel):
        emulator_wait: int = 60
        adb_timeout: int = 30
        system_port: int = 8200

    class IOSConfig(BaseModel):
        simulator_boot_timeout: int = 120
        wda_startup_retries: int = 3
        wda_local_port: int = 8100

    android: AndroidConfig = Field(default_factory=AndroidConfig)
    ios: IOSConfig = Field(default_factory=IOSConfig)


class MLConfig(BaseModel):
    """ML-related configuration"""
    contribute: bool = Field(default=True, description="Contribute anonymized data")
    update_check: str = Field(default="daily", description="Update check frequency")
    model_version: str = Field(default="2.0", description="Model version")
    confidence_threshold: float = Field(default=0.8, description="Prediction confidence threshold")


class IntegrationConfig(BaseModel):
    """External integrations configuration"""

    class SlackConfig(BaseModel):
        webhook_url: str = ""
        enabled: bool = False

    class GithubConfig(BaseModel):
        token: str = ""
        enabled: bool = False

    class JiraConfig(BaseModel):
        url: str = ""
        username: str = ""
        token: str = ""
        enabled: bool = False

    slack: SlackConfig = Field(default_factory=SlackConfig)
    github: GithubConfig = Field(default_factory=GithubConfig)
    jira: JiraConfig = Field(default_factory=JiraConfig)


class ObserveConfig(BaseModel):
    """
    Main configuration model for Observe Framework
    
    Supports:
    - YAML/JSON files
    - Environment variables
    - Profiles (dev, staging, prod)
    - Validation
    """
    framework: FrameworkConfig = Field(default_factory=FrameworkConfig)
    devices: DeviceConfig = Field(default_factory=DeviceConfig)
    ml: MLConfig = Field(default_factory=MLConfig)
    integrations: IntegrationConfig = Field(default_factory=IntegrationConfig)

    @classmethod
    def from_file(cls, path: Path) -> "ObserveConfig":
        """Load configuration from YAML/JSON file"""
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r") as f:
            if path.suffix in [".yaml", ".yml"]:
                data = yaml.safe_load(f)
            elif path.suffix == ".json":
                import json
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported config format: {path.suffix}")

        # Handle None/empty data (e.g., empty YAML file returns None)
        if data is None:
            data = {}

        # Expand environment variables
        data = cls._expand_env_vars(data)

        return cls(**data)

    def to_file(self, path: Path) -> None:
        """Save configuration to YAML/JSON file"""
        data = self.model_dump()

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            if path.suffix in [".yaml", ".yml"]:
                yaml.dump(data, f, Dumper=Dumper, default_flow_style=False)
            elif path.suffix == ".json":
                import json
                json.dump(data, f, indent=2)
            else:
                raise ValueError(f"Unsupported config format: {path.suffix}")

    @staticmethod
    def _expand_env_vars(data: Any) -> Any:
        """Recursively expand environment variables like ${VAR}"""
        if isinstance(data, dict):
            return {k: ObserveConfig._expand_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [ObserveConfig._expand_env_vars(item) for item in data]
        elif isinstance(data, str) and data.startswith("${") and data.endswith("}"):
            var_name = data[2:-1]
            return os.getenv(var_name, data)
        else:
            return data

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get config value by dot-notation key
        
        Example:
            config.get("framework.timeout")
            config.get("devices.android.adb_timeout")
        """
        parts = key.split(".")
        value = self.model_dump()

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set config value by dot-notation key
        
        Example:
            config.set("framework.timeout", 60)
        """
        parts = key.split(".")

        # Navigate to parent and set value
        obj: Any = self
        for part in parts[:-1]:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise ValueError(f"Invalid config key: {key}")

        last_part = parts[-1]
        if hasattr(obj, last_part):
            setattr(obj, last_part, value)
        else:
            raise ValueError(f"Invalid config key: {key}")


class ConfigManager:
    """
    Configuration manager with profile support
    
    Features:
    - Multiple profiles (dev, staging, prod)
    - Config file discovery
    - Environment variable overrides
    - Validation
    """

    DEFAULT_CONFIG_PATHS = [
        Path(".observe.yaml"),
        Path(".observe.yml"),
        Path("observe.yaml"),
        Path("observe.yml"),
        Path("config/observe.yaml"),
    ]

    def __init__(self, config_path: Optional[Path] = None, profile: str = "default"):
        self.profile = profile
        self.config_path = config_path or self._find_config()
        self.config = self._load_config()

    def _find_config(self) -> Path:
        """Find configuration file in common locations"""
        for path in self.DEFAULT_CONFIG_PATHS:
            if path.exists():
                return path

        # Return default path (will create if needed)
        return Path(".observe.yaml")

    def _load_config(self) -> ObserveConfig:
        """Load configuration from file or create default"""
        if self.config_path.exists():
            return ObserveConfig.from_file(self.config_path)
        else:
            # Return default config
            return ObserveConfig()

    def save(self) -> None:
        """Save current configuration to file"""
        self.config.to_file(self.config_path)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        """Set configuration value"""
        self.config.set(key, value)
        if save:
            self.save()

    def validate(self) -> list[str]:
        """
        Validate configuration
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check framework config
        if self.config.framework.timeout < 1:
            errors.append("framework.timeout must be >= 1")

        if self.config.framework.retry_count < 0:
            errors.append("framework.retry_count must be >= 0")

        if self.config.framework.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            errors.append("framework.log_level must be DEBUG/INFO/WARNING/ERROR")

        # Check ML config
        if not 0 <= self.config.ml.confidence_threshold <= 1:
            errors.append("ml.confidence_threshold must be between 0 and 1")

        # Check integrations
        if self.config.integrations.slack.enabled and not self.config.integrations.slack.webhook_url:
            errors.append("integrations.slack.webhook_url required when enabled")

        if self.config.integrations.github.enabled and not self.config.integrations.github.token:
            errors.append("integrations.github.token required when enabled")

        return errors

    def init_default(self) -> None:
        """Create default configuration file"""
        if self.config_path.exists():
            raise FileExistsError(f"Config already exists: {self.config_path}")

        self.config = ObserveConfig()
        self.save()

    def list_all(self) -> dict[str, Any]:
        """List all configuration values"""
        return self.config.model_dump()
