"""
Correlation Strategies

Different strategies for correlating events based on various signals.
"""

from typing import List, Optional, Dict, Any

from framework.correlation.types import CorrelationStrength, CorrelationMethod


class CorrelationStrategy:
    """Base class for correlation strategies"""

    def correlate(
            self,
            ui_event: Dict[str, Any],
            api_event: Dict[str, Any]
    ) -> tuple[bool, CorrelationStrength, List[CorrelationMethod], float]:
        """
        Check if two events are correlated

        Returns:
            (is_correlated, strength, methods, confidence_score)
        """
        raise NotImplementedError


class CorrelationIDStrategy(CorrelationStrategy):
    """
    Correlate events using explicit correlation IDs

    This is the strongest correlation method - events with the same
    correlation_id are definitively related.
    """

    def correlate(
            self,
            ui_event: Dict[str, Any],
            api_event: Dict[str, Any]
    ) -> tuple[bool, CorrelationStrength, List[CorrelationMethod], float]:
        ui_corr_id = ui_event.get('correlationId') or ui_event.get('correlation_id')
        api_corr_id = api_event.get('correlationId') or api_event.get('correlation_id')

        if ui_corr_id and api_corr_id and ui_corr_id == api_corr_id:
            return (
                True,
                CorrelationStrength.STRONG,
                [CorrelationMethod.CORRELATION_ID],
                1.0
            )

        return (False, CorrelationStrength.NONE, [], 0.0)


class TemporalProximityStrategy(CorrelationStrategy):
    """
    Correlate events based on temporal proximity

    Events that occur close together in time are likely related.
    """

    def __init__(self, max_time_delta_ms: int = 5000):
        """
        Args:
            max_time_delta_ms: Maximum time difference in milliseconds
        """
        self.max_time_delta_ms = max_time_delta_ms

    def correlate(
            self,
            ui_event: Dict[str, Any],
            api_event: Dict[str, Any]
    ) -> tuple[bool, CorrelationStrength, List[CorrelationMethod], float]:

        ui_time = ui_event.get('timestamp', 0)
        api_time = api_event.get('timestamp', 0)

        # API should happen AFTER UI event
        time_delta = api_time - ui_time

        if time_delta < 0 or time_delta > self.max_time_delta_ms:
            return (False, CorrelationStrength.NONE, [], 0.0)

        # Calculate confidence based on proximity
        # Closer events = higher confidence
        confidence = 1.0 - (time_delta / self.max_time_delta_ms)

        # Determine strength
        if time_delta < 500:  # Within 500ms
            strength = CorrelationStrength.MEDIUM
        elif time_delta < 2000:  # Within 2s
            strength = CorrelationStrength.WEAK
        else:  # Within max_time_delta
            strength = CorrelationStrength.WEAK
            confidence *= 0.5  # Lower confidence for distant events

        return (
            True,
            strength,
            [CorrelationMethod.TEMPORAL],
            confidence
        )


class ThreadCorrelationStrategy(CorrelationStrategy):
    """
    Correlate events based on thread/coroutine information

    Events in the same thread are likely related.
    """

    def correlate(
            self,
            ui_event: Dict[str, Any],
            api_event: Dict[str, Any]
    ) -> tuple[bool, CorrelationStrength, List[CorrelationMethod], float]:

        ui_thread = ui_event.get('threadId') or ui_event.get('thread_id')
        api_thread = api_event.get('threadId') or api_event.get('thread_id')

        if not ui_thread or not api_thread:
            return (False, CorrelationStrength.NONE, [], 0.0)

        if ui_thread == api_thread:
            return (
                True,
                CorrelationStrength.MEDIUM,
                [CorrelationMethod.THREAD],
                0.7  # Medium confidence - thread correlation alone is not conclusive
            )

        return (False, CorrelationStrength.NONE, [], 0.0)


class ScreenContextStrategy(CorrelationStrategy):
    """
    Correlate events based on screen context

    UI events and API calls on the same screen are more likely related.
    """

    def correlate(
            self,
            ui_event: Dict[str, Any],
            api_event: Dict[str, Any]
    ) -> tuple[bool, CorrelationStrength, List[CorrelationMethod], float]:

        ui_screen = ui_event.get('screen')
        api_screen = api_event.get('screen')

        if not ui_screen or not api_screen:
            return (False, CorrelationStrength.NONE, [], 0.0)

        if ui_screen == api_screen:
            # Same screen - provides context but not conclusive
            return (
                True,
                CorrelationStrength.WEAK,
                [CorrelationMethod.CAUSALITY],
                0.4
            )

        return (False, CorrelationStrength.NONE, [], 0.0)


class HybridCorrelationStrategy(CorrelationStrategy):
    """
    Combine multiple strategies for stronger correlation

    Uses multiple signals to establish correlation with higher confidence.
    """

    def __init__(self, strategies: Optional[List[CorrelationStrategy]] = None):
        self.strategies = strategies or [
            CorrelationIDStrategy(),
            TemporalProximityStrategy(),
            ThreadCorrelationStrategy(),
            ScreenContextStrategy()
        ]

    def correlate(
            self,
            ui_event: Dict[str, Any],
            api_event: Dict[str, Any]
    ) -> tuple[bool, CorrelationStrength, List[CorrelationMethod], float]:

        correlations = []
        methods = []

        for strategy in self.strategies:
            is_correlated, strength, strategy_methods, confidence = strategy.correlate(
                ui_event, api_event
            )

            if is_correlated:
                correlations.append((strength, confidence))
                methods.extend(strategy_methods)

        if not correlations:
            return (False, CorrelationStrength.NONE, [], 0.0)

        # Combine confidences
        total_confidence = sum(c for _, c in correlations) / len(correlations)

        # Determine overall strength
        strengths = [s for s, _ in correlations]

        if CorrelationStrength.STRONG in strengths:
            overall_strength = CorrelationStrength.STRONG
        elif len(correlations) >= 2:  # Multiple correlations
            overall_strength = CorrelationStrength.STRONG
            total_confidence = min(0.9, total_confidence * 1.2)  # Boost confidence
        elif CorrelationStrength.MEDIUM in strengths:
            overall_strength = CorrelationStrength.MEDIUM
        else:
            overall_strength = CorrelationStrength.WEAK

        return (
            True,
            overall_strength,
            methods,
            min(1.0, total_confidence)
        )
