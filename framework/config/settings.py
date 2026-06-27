"""
Application settings and configuration management.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """
    Application configuration settings.

    Can be overridden via environment variables with RECORDER_ prefix.
    Example: RECORDER_LOG_LEVEL=DEBUG
    """

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Optional[Path] = Field(default=None, description="Log file path")
    rich_tracebacks: bool = Field(default=True, description="Enable Rich tracebacks")

    # Paths
    output_dir: Path = Field(default_factory=lambda: Path.cwd() / "output", description="Default output directory")
    temp_dir: Path = Field(default_factory=lambda: Path.cwd() / ".tmp", description="Temporary files directory")

    # Analysis
    max_complexity: int = Field(default=10, description="Max allowed cyclomatic complexity")
    max_nested_depth: int = Field(default=5, description="Max allowed nesting depth")

    # Code Generation
    page_objects_dir: str = Field(default="page_objects", description="Page objects directory name")
    features_dir: str = Field(default="features", description="BDD features directory name")
    api_clients_dir: str = Field(default="api_clients", description="API clients directory name")

    # Test Framework
    test_framework: str = Field(default="pytest", description="Test framework to use")
    bdd_framework: str = Field(default="pytest-bdd", description="BDD framework to use")

    # Performance
    parallel_workers: int = Field(default=4, description="Number of parallel workers")
    timeout_seconds: int = Field(default=300, description="Default operation timeout")

    # Feature Flags
    enable_ast_analysis: bool = Field(default=True, description="Enable AST analysis")
    enable_business_logic: bool = Field(default=True, description="Enable business logic analysis")
    enable_ml_features: bool = Field(default=False, description="Enable ML features (experimental)")

    class Config:
        env_prefix = "RECORDER_"
        case_sensitive = False

    @classmethod
    def from_env(cls) -> "Settings":
        """
        Create settings from environment variables.

        Returns:
            Settings instance with values from environment
        """
        env_vars = {}

        # Parse environment variables with RECORDER_ prefix
        for key, value in os.environ.items():
            if key.startswith("RECORDER_"):
                setting_name = key[9:].lower()  # Remove RECORDER_ prefix
                env_vars[setting_name] = value

        return cls(**env_vars)

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the global settings instance (singleton pattern).

    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
        _settings.ensure_directories()
    return _settings


def reset_settings() -> None:
    """Reset global settings (useful for testing)."""
    global _settings
    _settings = None
