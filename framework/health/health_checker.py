"""Health check command for CLI daemon."""

import time
from typing import Dict, Any

from framework.config.config_manager import ConfigManager


class HealthChecker:
    """Health checker for the CLI daemon."""

    def __init__(self):
        self.start_time = time.time()
        self.config = ConfigManager()

    def check(self) -> Dict[str, Any]:
        """
        Perform health check.
        
        Returns:
            Dict containing health status
        """
        from framework import __version__

        # Check if Rust core is available
        rust_core_available = False
        try:
            import observe_core
            rust_core_available = True
        except ImportError:
            pass

        uptime = int(time.time() - self.start_time)

        return {
            "status": "ok",
            "version": __version__ if hasattr(__version__, '__version__') else "0.5.0",
            "rust_core": rust_core_available,
            "uptime_seconds": uptime
        }
