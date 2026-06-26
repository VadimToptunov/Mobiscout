"""
Pattern recognizer for detecting common user flows and critical paths.

Uses clustering and sequential pattern mining to identify frequently used flows.
"""

import logging
from collections import defaultdict, Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class FlowPattern:
    """Detected flow pattern."""
    pattern_id: str
    screens: List[str]
    frequency: int
    confidence: float
    is_critical: bool
    description: str


@dataclass
class AnomalyDetection:
    """Detected anomaly in user flow."""
    session_id: str
    timestamp: int
    anomaly_type: str
    description: str
    severity: str  # 'low', 'medium', 'high'


class PatternRecognizer:
    """
    Flow pattern recognition and anomaly detection.

    Features:
    - Detect common user flows
    - Identify critical paths
    - Find flow anomalies
    - Suggest test scenarios
    """

    def __init__(self, min_support: int = 2, min_confidence: float = 0.6):
        """
        Initialize pattern recognizer.

        Args:
            min_support: Minimum frequency for pattern to be considered
            min_confidence: Minimum confidence for pattern detection
        """
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.detected_patterns: List[FlowPattern] = []
        self.detected_anomalies: List[AnomalyDetection] = []

    def analyze_flows(
            self,
            navigation_events: List[Dict[str, Any]]
    ) -> List[FlowPattern]:
        """
        Analyze navigation events to detect common flows.

        Args:
            navigation_events: List of NavigationEvent data

        Returns:
            List of detected patterns
        """
        # Group events by session
        sessions = self._group_by_session(navigation_events)

        # Extract sequences
        sequences = []
        for session_id, events in sessions.items():
            sequence = self._extract_sequence(events)
            if len(sequence) > 1:
                sequences.append(sequence)

        # Find frequent patterns
        patterns = self._mine_sequential_patterns(sequences)

        # Identify critical paths
        self._mark_critical_paths(patterns, sequences)

        self.detected_patterns = patterns

        logger.info(f"Detected {len(patterns)} flow patterns")

        return patterns

    def _group_by_session(
            self,
            events: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group events by session ID."""
        sessions = defaultdict(list)

        for event in events:
            session_id = event.get('session_id') or event.get('sessionId')
            if session_id:
                sessions[session_id].append(event)

        # Sort each session by timestamp
        for session_id in sessions:
            sessions[session_id].sort(key=lambda e: e.get('timestamp', 0))

        return dict(sessions)

    def _extract_sequence(self, events: List[Dict[str, Any]]) -> List[str]:
        """Extract screen sequence from events."""
        sequence = []
        prev_screen = None

        for event in events:
            screen = event.get('to_screen') or event.get('screen')

            if screen and screen != prev_screen:
                sequence.append(screen)
                prev_screen = screen

        return sequence

    def _mine_sequential_patterns(
            self,
            sequences: List[List[str]]
    ) -> List[FlowPattern]:
        """
        Mine frequent sequential patterns.

        Uses a simple sequential pattern mining algorithm.
        """
        patterns = []

        # Find patterns of length 2, 3, 4, 5
        for length in range(2, 6):
            length_patterns = self._find_patterns_of_length(sequences, length)
            patterns.extend(length_patterns)

        return patterns

    def _find_patterns_of_length(
            self,
            sequences: List[List[str]],
            length: int
    ) -> List[FlowPattern]:
        """Find all patterns of specific length."""
        pattern_counts = Counter()

        # Count subsequences
        for sequence in sequences:
            for i in range(len(sequence) - length + 1):
                subsequence = tuple(sequence[i:i + length])
                pattern_counts[subsequence] += 1

        # Filter by min_support
        patterns = []
        for pattern, count in pattern_counts.items():
            if count >= self.min_support:
                confidence = count / len(sequences)

                if confidence >= self.min_confidence:
                    pattern_id = f"pattern_{len(patterns) + 1}"
                    description = " → ".join(pattern)

                    flow_pattern = FlowPattern(
                        pattern_id=pattern_id,
                        screens=list(pattern),
                        frequency=count,
                        confidence=confidence,
                        is_critical=False,  # Will be determined later
                        description=description
                    )

                    patterns.append(flow_pattern)

        return patterns

    def _mark_critical_paths(
            self,
            patterns: List[FlowPattern],
            sequences: List[List[str]]
    ):
        """Mark patterns that are likely critical paths."""
        # Critical path heuristics:
        # 1. High frequency (> 50% of sessions)
        # 2. Starts from login/onboarding
        # 3. Contains transaction screens

        total_sessions = len(sequences)
        critical_screens = {'login', 'home', 'checkout', 'payment', 'confirm', 'kyc'}
        entry_screens = {'onboarding', 'splash', 'login'}

        for pattern in patterns:
            # High frequency check
            frequency_ratio = pattern.frequency / total_sessions

            # Entry screen check
            starts_with_entry = any(
                pattern.screens[0].lower().find(screen) >= 0
                for screen in entry_screens
            )

            # Contains critical screen check
            contains_critical = any(
                any(screen_name.lower().find(critical) >= 0 for critical in critical_screens)
                for screen_name in pattern.screens
            )

            # Mark as critical if conditions met
            if frequency_ratio > 0.5 or (starts_with_entry and contains_critical):
                pattern.is_critical = True

    def detect_anomalies(
            self,
            navigation_events: List[Dict[str, Any]],
            known_patterns: Optional[List[FlowPattern]] = None
    ) -> List[AnomalyDetection]:
        """
        Detect anomalies in user flows.

        Args:
            navigation_events: Navigation events to analyze
            known_patterns: Known normal patterns (optional)

        Returns:
            List of detected anomalies
        """
        if known_patterns is None:
            known_patterns = self.detected_patterns

        anomalies = []

        # Group by session
        sessions = self._group_by_session(navigation_events)

        for session_id, events in sessions.items():
            sequence = self._extract_sequence(events)

            # Detect various anomaly types
            anomalies.extend(self._detect_dead_ends(session_id, sequence))
            anomalies.extend(self._detect_loops(session_id, sequence))
            anomalies.extend(self._detect_unusual_paths(session_id, sequence, known_patterns))

        self.detected_anomalies = anomalies

        logger.info(f"Detected {len(anomalies)} anomalies")

        return anomalies

    def _detect_dead_ends(
            self,
            session_id: str,
            sequence: List[str]
    ) -> List[AnomalyDetection]:
        """Detect sessions that end unexpectedly."""
        anomalies = []

        # Check if session ended abruptly (not at expected exit point)
        exit_screens = {'home', 'logout', 'onboarding'}

        if len(sequence) > 2:
            last_screen = sequence[-1].lower()

            # If last screen is not a typical exit point and sequence is short
            if not any(exit_screen in last_screen for exit_screen in exit_screens):
                if len(sequence) < 5:  # Short session with unusual exit
                    anomaly = AnomalyDetection(
                        session_id=session_id,
                        timestamp=0,  # Would need actual timestamp
                        anomaly_type='dead_end',
                        description=f"Session ended at unexpected screen: {last_screen}",
                        severity='medium'
                    )
                    anomalies.append(anomaly)

        return anomalies

    def _detect_loops(
            self,
            session_id: str,
            sequence: List[str]
    ) -> List[AnomalyDetection]:
        """Detect navigation loops (screen revisited multiple times)."""
        anomalies = []

        # Count screen visits
        screen_counts = Counter(sequence)

        # Find screens visited more than 3 times
        for screen, count in screen_counts.items():
            if count > 3:
                anomaly = AnomalyDetection(
                    session_id=session_id,
                    timestamp=0,
                    anomaly_type='navigation_loop',
                    description=f"Screen '{screen}' visited {count} times (possible loop)",
                    severity='low' if count <= 5 else 'medium'
                )
                anomalies.append(anomaly)

        return anomalies

    def _detect_unusual_paths(
            self,
            session_id: str,
            sequence: List[str],
            known_patterns: List[FlowPattern]
    ) -> List[AnomalyDetection]:
        """Detect paths that don't match any known pattern."""
        if not known_patterns:
            return []

        anomalies = []

        # Check if sequence contains any known pattern
        matches_pattern = False

        for pattern in known_patterns:
            if self._sequence_contains_pattern(sequence, pattern.screens):
                matches_pattern = True
                break

        # If sequence doesn't match any pattern and is long enough
        if not matches_pattern and len(sequence) >= 3:
            anomaly = AnomalyDetection(
                session_id=session_id,
                timestamp=0,
                anomaly_type='unusual_path',
                description=f"Unusual navigation path: {' → '.join(sequence[:5])}...",
                severity='low'
            )
            anomalies.append(anomaly)

        return anomalies

    def _sequence_contains_pattern(
            self,
            sequence: List[str],
            pattern: List[str]
    ) -> bool:
        """Check if sequence contains pattern as subsequence."""
        pattern_len = len(pattern)

        for i in range(len(sequence) - pattern_len + 1):
            if sequence[i:i + pattern_len] == pattern:
                return True

        return False

    def suggest_test_scenarios(
            self,
            patterns: Optional[List[FlowPattern]] = None
    ) -> List[Dict[str, Any]]:
        """
        Suggest test scenarios based on detected patterns.

        Args:
            patterns: Flow patterns (uses detected if not provided)

        Returns:
            List of test scenario suggestions
        """
        if patterns is None:
            patterns = self.detected_patterns

        scenarios = []

        # Prioritize critical paths
        critical_patterns = [p for p in patterns if p.is_critical]

        for pattern in critical_patterns:
            scenario = {
                'pattern_id': pattern.pattern_id,
                'priority': 'critical' if pattern.is_critical else 'normal',
                'frequency': pattern.frequency,
                'confidence': pattern.confidence,
                'steps': pattern.screens,
                'gherkin': self._generate_gherkin(pattern),
                'description': pattern.description
            }
            scenarios.append(scenario)

        # Add high-frequency non-critical patterns
        frequent_patterns = [
            p for p in patterns
            if not p.is_critical and p.frequency > self.min_support * 2
        ]

        for pattern in frequent_patterns[:5]:  # Limit to top 5
            scenario = {
                'pattern_id': pattern.pattern_id,
                'priority': 'normal',
                'frequency': pattern.frequency,
                'confidence': pattern.confidence,
                'steps': pattern.screens,
                'gherkin': self._generate_gherkin(pattern),
                'description': pattern.description
            }
            scenarios.append(scenario)

        logger.info(f"Generated {len(scenarios)} test scenario suggestions")

        return scenarios

    def _generate_gherkin(self, pattern: FlowPattern) -> str:
        """Generate Gherkin scenario from pattern."""
        lines = []

        # Scenario header
        scenario_name = pattern.description.replace(' → ', ' to ')
        lines.append(f"Scenario: User navigates {scenario_name}")

        # Given step (first screen)
        lines.append(f"  Given user is on {pattern.screens[0]} screen")

        # When/And steps (intermediate screens)
        for i in range(1, len(pattern.screens) - 1):
            lines.append(f"  When user navigates to {pattern.screens[i]} screen")

        # Then step (last screen)
        lines.append(f"  Then user should see {pattern.screens[-1]} screen")

        return "\n".join(lines)

    def get_pattern_stats(self) -> Dict[str, Any]:
        """Get statistics about detected patterns."""
        if not self.detected_patterns:
            return {
                'total_patterns': 0,
                'critical_patterns': 0,
                'avg_frequency': 0.0,
                'avg_confidence': 0.0
            }

        critical_count = sum(1 for p in self.detected_patterns if p.is_critical)
        avg_frequency = sum(p.frequency for p in self.detected_patterns) / len(self.detected_patterns)
        avg_confidence = sum(p.confidence for p in self.detected_patterns) / len(self.detected_patterns)

        return {
            'total_patterns': len(self.detected_patterns),
            'critical_patterns': critical_count,
            'avg_frequency': avg_frequency,
            'avg_confidence': avg_confidence,
            'patterns_by_length': self._count_by_length()
        }

    def _count_by_length(self) -> Dict[int, int]:
        """Count patterns by length."""
        counts = defaultdict(int)

        for pattern in self.detected_patterns:
            length = len(pattern.screens)
            counts[length] += 1

        return dict(counts)
