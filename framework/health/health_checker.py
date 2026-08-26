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
            # __version__ is a plain string: the old hasattr(__version__, "__version__")
            # guard was never true, so every client was told the engine was 0.5.0.
            "version": __version__,
            "uptime_seconds": uptime,
        }
