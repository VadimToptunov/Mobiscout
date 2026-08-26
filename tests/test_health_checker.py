"""The daemon's health/check payload. It is what every client (and every bug
report) reads the engine version from, so the version must be the real one."""

from framework import __version__
from framework.health.health_checker import HealthChecker


def test_check_reports_the_real_engine_version():
    """Regression: the old `hasattr(__version__, "__version__")` guard was never
    true for a plain string, so every client was told the engine was 0.5.0."""
    result = HealthChecker().check()
    assert result["version"] == __version__
    assert result["version"] != "0.5.0" or __version__ == "0.5.0"


def test_check_reports_status_and_uptime():
    result = HealthChecker().check()
    assert result["status"] == "ok"
    assert isinstance(result["uptime_seconds"], int) and result["uptime_seconds"] >= 0
