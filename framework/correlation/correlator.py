"""
Event Correlator

Main correlation engine that analyzes events and builds correlations.
Supports both high-performance Rust implementation and Python fallback.
"""

import logging
import time
from typing import List, Dict, Any, Optional

from framework.correlation.strategies import HybridCorrelationStrategy, TemporalProximityStrategy
from framework.correlation.types import (
    CorrelationResult,
    UIToAPICorrelation,
    APIToNavigationCorrelation,
    FullFlowCorrelation,
    CorrelationStrength,
    CorrelationMethod,
)
from framework.storage.event_store import EventStore

# Try to import Rust core for 16-90x performance improvement
try:
    from rust_core import RustCorrelator

    USE_RUST = True
    logger = logging.getLogger(__name__)
    logger.info("Using high-performance Rust correlation engine (16-90x faster)")
except ImportError:
    USE_RUST = False
    logger = logging.getLogger(__name__)
    logger.warning(
        "Rust core not available, using Python fallback. "
        "Install Rust core for 16-90x performance improvement: cd rust_core && maturin develop"
    )


class EventCorrelator:
    """
    Correlates events to understand application behavior

    Takes raw events (UI, API, Navigation) and builds correlations:
    - UI event → API call(s)
    - API response → Navigation
    - Full flows: UI → API → Navigation

    Performance: Uses Rust implementation when available for 16-90x speedup.
    """

    def __init__(self, event_store: Optional[EventStore] = None, force_python: bool = False):
        """
        Initialize correlator

        Args:
            event_store: Optional EventStore for loading events
            force_python: Force Python implementation even if Rust is available (for testing)
        """
        self.event_store = event_store
        self.use_rust = USE_RUST and not force_python

        # Initialize strategies
        self.ui_strategy = HybridCorrelationStrategy()
        self.nav_strategy = TemporalProximityStrategy(max_time_delta_ms=3000)

        # Initialize Rust correlator if available
        if self.use_rust:
            self.rust_correlator = RustCorrelator()

        self.logger = logging.getLogger(__name__)

    def correlate_session(self, session_id: str) -> CorrelationResult:
        """
        Correlate all events in a session

        Args:
            session_id: Session ID to analyze

        Returns:
            CorrelationResult with all correlations
        """
        if not self.event_store:
            raise ValueError("EventStore required for session correlation")

        # Load events from store
        ui_events = self.event_store.get_events(session_id=session_id, event_type="UIEvent")
        api_events = self.event_store.get_events(session_id=session_id, event_type="NetworkEvent")
        nav_events = self.event_store.get_events(session_id=session_id, event_type="NavigationEvent")

        # Convert to dicts for processing
        ui_dicts = [self._event_to_dict(e) for e in ui_events]
        api_dicts = [self._event_to_dict(e) for e in api_events]
        nav_dicts = [self._event_to_dict(e) for e in nav_events]

        return self.correlate_events(
            session_id=session_id, ui_events=ui_dicts, api_events=api_dicts, navigation_events=nav_dicts
        )

    def correlate_events(
            self,
            session_id: str,
            ui_events: List[Dict[str, Any]],
            api_events: List[Dict[str, Any]],
            navigation_events: List[Dict[str, Any]],
    ) -> CorrelationResult:
        """
        Correlate provided events

        Args:
            session_id: Session identifier
            ui_events: List of UI event dicts
            api_events: List of API/network event dicts
            navigation_events: List of navigation event dicts

        Returns:
            CorrelationResult with all correlations
        """
        start_time = time.time()

        # Try Rust implementation first for 16-90x performance improvement
        if self.use_rust:
            try:
                result = self._correlate_with_rust(
                    session_id, ui_events, api_events, navigation_events
                )
                elapsed = time.time() - start_time
                self.logger.info(
                    f"Rust correlation completed in {elapsed * 1000:.2f}ms "
                    f"({len(ui_events)} UI, {len(api_events)} API, "
                    f"{len(navigation_events)} nav events)"
                )
                return result
            except Exception as e:
                self.logger.warning(
                    f"Rust correlation failed, falling back to Python: {e}"
                )
                # Fall through to Python implementation

        # Python fallback implementation
        result = self._correlate_with_python(
            session_id, ui_events, api_events, navigation_events
        )

        elapsed = time.time() - start_time
        self.logger.info(
            f"Python correlation completed in {elapsed * 1000:.2f}ms "
            f"({len(ui_events)} UI, {len(api_events)} API, "
            f"{len(navigation_events)} nav events)"
        )

        return result

    def _correlate_with_rust(
            self,
            session_id: str,
            ui_events: List[Dict[str, Any]],
            api_events: List[Dict[str, Any]],
            navigation_events: List[Dict[str, Any]],
    ) -> CorrelationResult:
        """Correlate using high-performance Rust implementation"""
        # Use Rust correlator
        rust_result = self.rust_correlator.correlate_events(
            ui_events, api_events, navigation_events
        )

        # Convert Rust result to Python CorrelationResult
        return CorrelationResult(
            session_id=session_id,
            ui_to_api=rust_result.ui_to_api,
            api_to_navigation=rust_result.api_to_navigation,
            full_flows=rust_result.full_flows,
            total_ui_events=len(ui_events),
            total_api_events=len(api_events),
            total_navigation_events=len(navigation_events),
            correlated_ui_events=rust_result.correlated_ui_events,
            correlated_api_events=rust_result.correlated_api_events,
            correlation_rate=rust_result.correlation_rate,
            statistics=rust_result.statistics,
        )

    def _correlate_with_python(
            self,
            session_id: str,
            ui_events: List[Dict[str, Any]],
            api_events: List[Dict[str, Any]],
            navigation_events: List[Dict[str, Any]],
    ) -> CorrelationResult:
        """Correlate using Python implementation (fallback)"""
        # Correlate UI → API
        ui_to_api = self._correlate_ui_to_api(ui_events, api_events)

        # Correlate API → Navigation
        api_to_nav = self._correlate_api_to_navigation(api_events, navigation_events)

        # Build full flows
        full_flows = self._build_full_flows(ui_to_api, api_to_nav)

        # Calculate statistics
        correlated_ui = len([c for c in ui_to_api if c.api_calls])
        correlated_api = len(set(call["eventId"] for c in ui_to_api for call in c.api_calls if "eventId" in call))

        correlation_rate = 0.0
        if ui_events:
            correlation_rate = correlated_ui / len(ui_events)

        return CorrelationResult(
            session_id=session_id,
            ui_to_api=ui_to_api,
            api_to_navigation=api_to_nav,
            full_flows=full_flows,
            total_ui_events=len(ui_events),
            total_api_events=len(api_events),
            total_navigation_events=len(navigation_events),
            correlated_ui_events=correlated_ui,
            correlated_api_events=correlated_api,
            correlation_rate=correlation_rate,
            statistics={
                "ui_to_api_count": len(ui_to_api),
                "api_to_nav_count": len(api_to_nav),
                "full_flows_count": len(full_flows),
                "strong_correlations": len([c for c in ui_to_api if c.strength == CorrelationStrength.STRONG]),
            },
        )

    def _correlate_ui_to_api(
            self, ui_events: List[Dict[str, Any]], api_events: List[Dict[str, Any]]
    ) -> List[UIToAPICorrelation]:
        """
        Correlate UI events with API calls

        For each UI event, find associated API calls using correlation strategies.
        """
        correlations = []

        for ui_event in ui_events:
            # Find API calls that might be related to this UI event
            correlated_apis = []

            for api_event in api_events:
                # Check correlation using hybrid strategy
                is_correlated, strength, methods, confidence = self.ui_strategy.correlate(ui_event, api_event)

                if is_correlated:
                    correlated_apis.append(
                        {
                            "eventId": api_event.get("eventId", ""),
                            "method": api_event.get("method", ""),
                            "endpoint": api_event.get("url", ""),
                            "statusCode": api_event.get("statusCode"),
                            "timestamp": api_event.get("timestamp", 0),
                            "duration": api_event.get("duration", 0),
                            "correlationMethods": [m.value for m in methods],
                            "confidence": confidence,
                        }
                    )

            # Create correlation only if we found related APIs
            if correlated_apis:
                # Determine overall strength
                confidences = [api["confidence"] for api in correlated_apis]
                avg_confidence = sum(confidences) / len(confidences)

                if avg_confidence >= 0.8:
                    strength = CorrelationStrength.STRONG
                elif avg_confidence >= 0.5:
                    strength = CorrelationStrength.MEDIUM
                else:
                    strength = CorrelationStrength.WEAK
                    # Keep avg_confidence as-is (don't overwrite to 0.0)
                    # This preserves the actual measured correlation strength

                # Calculate time delta
                time_delta = None
                if correlated_apis:
                    first_api_time = min(api["timestamp"] for api in correlated_apis)
                    time_delta = first_api_time - ui_event.get("timestamp", 0)

                correlation = UIToAPICorrelation(
                    ui_event_id=ui_event.get("eventId", ""),
                    ui_event_type=ui_event.get("action", "unknown"),
                    ui_element_id=ui_event.get("elementId"),
                    ui_screen=ui_event.get("screen", "unknown"),
                    ui_timestamp=ui_event.get("timestamp", 0),
                    api_calls=correlated_apis,
                    strength=strength,
                    methods=[CorrelationMethod.HYBRID],
                    confidence_score=avg_confidence,
                    time_delta_ms=time_delta,
                )

                correlations.append(correlation)

        return correlations

    def _correlate_api_to_navigation(
            self, api_events: List[Dict[str, Any]], nav_events: List[Dict[str, Any]]
    ) -> List[APIToNavigationCorrelation]:
        """
        Correlate API responses with navigation events

        API responses often trigger navigation (e.g., success → next screen, error → stay).
        """
        correlations = []

        for api_event in api_events:
            api_time = api_event.get("timestamp", 0)

            # Find navigation events that happen shortly after this API call
            for nav_event in nav_events:
                nav_time = nav_event.get("timestamp", 0)
                time_delta = nav_time - api_time

                # Navigation should happen after API response
                if time_delta < 0 or time_delta > 3000:  # Within 3 seconds
                    continue

                # Check if they're on the same screen context
                is_correlated, strength, methods, confidence = self.nav_strategy.correlate(api_event, nav_event)

                if is_correlated:
                    # Build condition based on status code
                    status_code = api_event.get("statusCode", 0)
                    condition = None
                    if 200 <= status_code < 300:
                        condition = "success"
                    elif status_code >= 400:
                        condition = "error"

                    correlation = APIToNavigationCorrelation(
                        api_event_id=api_event.get("eventId", ""),
                        api_method=api_event.get("method", ""),
                        api_endpoint=api_event.get("url", ""),
                        api_status_code=status_code,
                        api_timestamp=api_time,
                        navigation_event_id=nav_event.get("eventId", ""),
                        from_screen=nav_event.get("fromScreen", "unknown"),
                        to_screen=nav_event.get("toScreen", "unknown"),
                        navigation_timestamp=nav_time,
                        strength=strength,
                        methods=methods,
                        confidence_score=confidence,
                        time_delta_ms=time_delta,
                        condition=condition,
                    )

                    correlations.append(correlation)

        return correlations

    def _build_full_flows(
            self, ui_to_api: List[UIToAPICorrelation], api_to_nav: List[APIToNavigationCorrelation]
    ) -> List[FullFlowCorrelation]:
        """
        Build complete flows by combining UI→API and API→Navigation correlations

        Example: Tap Login → POST /auth/login → Navigate to Home
        """
        flows = []

        for ui_corr in ui_to_api:
            if not ui_corr.api_calls:
                continue

            # Find navigation events triggered by these API calls
            related_navs = []
            for api_call in ui_corr.api_calls:
                api_id = api_call.get("eventId", "")

                # Find navigation correlations for this API call
                navs = [nav_corr for nav_corr in api_to_nav if nav_corr.api_event_id == api_id]
                related_navs.extend(navs)

            if related_navs:
                # Determine overall strength
                nav_strengths = [nav.strength for nav in related_navs]
                if CorrelationStrength.STRONG in nav_strengths:
                    overall_strength = CorrelationStrength.STRONG
                elif CorrelationStrength.MEDIUM in nav_strengths:
                    overall_strength = CorrelationStrength.MEDIUM
                else:
                    overall_strength = CorrelationStrength.WEAK

                overall_confidence = (ui_corr.confidence_score + sum(nav.confidence_score for nav in related_navs)) / (
                        1 + len(related_navs)
                )
            else:
                # No navigation correlations found, use UI correlation values
                overall_strength = ui_corr.strength
                overall_confidence = ui_corr.confidence_score

            # Generate flow description
            description = self._generate_flow_description(ui_corr, related_navs)

            flow = FullFlowCorrelation(
                flow_id=f"flow_{ui_corr.ui_event_id}",
                flow_name=f"{ui_corr.ui_event_type}_on_{ui_corr.ui_screen}",
                ui_correlation=ui_corr,
                api_navigation_correlations=related_navs,
                overall_strength=overall_strength,
                overall_confidence=overall_confidence,
                description=description,
            )

            flows.append(flow)

        return flows

    def _generate_flow_description(
            self, ui_corr: UIToAPICorrelation, nav_corrs: List[APIToNavigationCorrelation]
    ) -> str:
        """Generate human-readable flow description"""
        parts = [f"User {ui_corr.ui_event_type} on {ui_corr.ui_screen}"]

        if ui_corr.api_calls:
            api_desc = ", ".join(
                [f"{api['method']} {api['endpoint']}" for api in ui_corr.api_calls[:2]]  # Limit to first 2
            )
            parts.append(f"triggers {api_desc}")

        if nav_corrs:
            nav_desc = ", ".join(
                [f"navigate to {nav.to_screen} ({nav.condition})" for nav in nav_corrs[:2]]  # Limit to first 2
            )
            parts.append(f"which causes {nav_desc}")

        return " → ".join(parts)

    def _event_to_dict(self, event: Any) -> Dict[str, Any]:
        """Convert event object to dict for processing"""
        if isinstance(event, dict):
            return event

        # Handle SQLite Row objects
        if hasattr(event, "keys"):
            return {key: event[key] for key in event.keys()}

        # Handle Pydantic models
        if hasattr(event, "model_dump"):
            result = event.model_dump()
            return result if isinstance(result, dict) else {}

        # Fallback
        return {}
