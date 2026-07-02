"""Runtime-protection analyzers (split out of the former runtime_protection god file)."""

from framework.security.runtime.base import (
    ProtectionCategory,
    ImplementationQuality,
    ProtectionIndicator,
    ProtectionAnalysis,
    ProtectionStatus,
    BypassMethod,
    RuntimeProtectionResult,
    QuickCheckResult,
)
from framework.security.runtime.android import AndroidProtectionAnalyzer
from framework.security.runtime.ios import IOSProtectionAnalyzer
from framework.security.runtime.analyzer import RuntimeProtectionAnalyzer

__all__ = [
    "ProtectionCategory",
    "ImplementationQuality",
    "ProtectionIndicator",
    "ProtectionAnalysis",
    "ProtectionStatus",
    "BypassMethod",
    "RuntimeProtectionResult",
    "QuickCheckResult",
    "AndroidProtectionAnalyzer",
    "IOSProtectionAnalyzer",
    "RuntimeProtectionAnalyzer",
]
