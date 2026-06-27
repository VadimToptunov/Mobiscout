"""
Event Correlation Engine

This module provides correlation between UI events, API calls, and navigation events
to build a comprehensive understanding of application behavior.
"""

from framework.correlation.correlator import EventCorrelator
from framework.correlation.types import (
    CorrelationResult,
    UIToAPICorrelation,
    APIToNavigationCorrelation,
    CorrelationStrength,
)

__all__ = [
    "EventCorrelator",
    "CorrelationResult",
    "UIToAPICorrelation",
    "APIToNavigationCorrelation",
    "CorrelationStrength",
]
