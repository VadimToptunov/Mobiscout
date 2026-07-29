"""Health check command for CLI daemon."""

import time
from typing import Dict, Any

from framework.config.config_manager import ConfigManager


class HealthChecker:
    """Health checker for the CLI daemon."""

    def __init__(self) -> None:
        self.start_time = time.time()
        self.config = ConfigManager()

    def check(self) -> Dict[str, Any]:
        """
        Perform health check.

        Returns:
            Dict containing health status
        """
        from framework import __version__

        uptime = int(time.time() - self.start_time)

        return {
            "status": "ok",
            "version": __version__ if hasattr(__version__, "__version__") else "0.5.0",
            "uptime_seconds": uptime,
        }
