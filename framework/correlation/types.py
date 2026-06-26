"""
Correlation Types

Data structures for representing correlations between events.
"""

from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class CorrelationStrength(str, Enum):
    """Strength of correlation between events"""
    STRONG = "strong"  # High confidence (e.g., same correlation_id)
    MEDIUM = "medium"  # Medium confidence (e.g., temporal + thread match)
    WEAK = "weak"  # Low confidence (e.g., only temporal proximity)
    NONE = "none"  # No correlation detected


class CorrelationMethod(str, Enum):
    """Method used to establish correlation"""
    CORRELATION_ID = "correlation_id"  # Explicit correlation ID matching
    TEMPORAL = "temporal"  # Time-based proximity
    THREAD = "thread"  # Same thread/coroutine
    CAUSALITY = "causality"  # Causal relationship detected
    HYBRID = "hybrid"  # Multiple methods combined


class UIToAPICorrelation(BaseModel):
    """
    Correlation between a UI interaction and one or more API calls

    Example: User taps "Login" button → POST /auth/login
    """
    ui_event_id: str = Field(description="ID of the UI event")
    ui_event_type: str = Field(description="Type of UI event (tap, swipe, input)")
    ui_element_id: Optional[str] = Field(default=None, description="Element identifier")
    ui_screen: str = Field(description="Screen where UI event occurred")
    ui_timestamp: int = Field(description="Timestamp of UI event (ms)")

    api_calls: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of correlated API calls"
    )

    strength: CorrelationStrength = Field(description="Correlation strength")
    methods: List[CorrelationMethod] = Field(
        default_factory=list,
        description="Methods used to establish correlation"
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0)"
    )

    time_delta_ms: Optional[int] = Field(
        default=None,
        description="Time between UI event and first API call (ms)"
    )

    notes: Optional[str] = Field(default=None, description="Additional notes")


class APIToNavigationCorrelation(BaseModel):
    """
    Correlation between API response and navigation event

    Example: POST /auth/login returns 200 → Navigate to HomeScreen
    """
    api_event_id: str = Field(description="ID of the API event")
    api_method: str = Field(description="HTTP method")
    api_endpoint: str = Field(description="API endpoint")
    api_status_code: int = Field(description="HTTP status code")
    api_timestamp: int = Field(description="Timestamp of API response (ms)")

    navigation_event_id: str = Field(description="ID of navigation event")
    from_screen: str = Field(description="Source screen")
    to_screen: str = Field(description="Destination screen")
    navigation_timestamp: int = Field(description="Timestamp of navigation (ms)")

    strength: CorrelationStrength = Field(description="Correlation strength")
    methods: List[CorrelationMethod] = Field(
        default_factory=list,
        description="Methods used to establish correlation"
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0)"
    )

    time_delta_ms: int = Field(description="Time between API response and navigation (ms)")

    condition: Optional[str] = Field(
        default=None,
        description="Condition that triggered navigation (e.g., 'status_code == 200')"
    )


class FullFlowCorrelation(BaseModel):
    """
    Complete flow correlation: UI → API → Navigation

    Example:
      Tap Login → POST /auth/login → Navigate to Home (on success)
                                   → Stay on Login (on error)
    """
    flow_id: str = Field(description="Unique flow identifier")
    flow_name: Optional[str] = Field(default=None, description="Human-readable flow name")

    ui_correlation: UIToAPICorrelation
    api_navigation_correlations: List[APIToNavigationCorrelation] = Field(
        default_factory=list,
        description="Possible navigation outcomes"
    )

    overall_strength: CorrelationStrength
    overall_confidence: float = Field(ge=0.0, le=1.0)

    description: Optional[str] = Field(
        default=None,
        description="Auto-generated flow description"
    )


class CorrelationResult(BaseModel):
    """
    Complete correlation analysis result for a session
    """
    session_id: str = Field(description="Session ID")

    ui_to_api: List[UIToAPICorrelation] = Field(
        default_factory=list,
        description="All UI→API correlations"
    )

    api_to_navigation: List[APIToNavigationCorrelation] = Field(
        default_factory=list,
        description="All API→Navigation correlations"
    )

    full_flows: List[FullFlowCorrelation] = Field(
        default_factory=list,
        description="Complete flows (UI→API→Navigation)"
    )

    total_ui_events: int = Field(default=0)
    total_api_events: int = Field(default=0)
    total_navigation_events: int = Field(default=0)

    correlated_ui_events: int = Field(default=0, description="UI events with API correlations")
    correlated_api_events: int = Field(default=0, description="API calls with correlations")

    correlation_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall correlation success rate"
    )

    statistics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional statistics"
    )
