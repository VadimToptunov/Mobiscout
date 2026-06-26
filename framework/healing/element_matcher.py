"""
Element matcher

Uses ML model to match correct element from alternatives.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict

from .selector_discovery import AlternativeSelector


@dataclass
class MatchResult:
    """Result of element matching"""
    selector: AlternativeSelector
    ml_confidence: float  # From ML model
    combined_confidence: float  # ML + selector confidence
    reasoning: str

    def __repr__(self):
        return f"MatchResult({self.selector.strategy.value}, confidence={self.combined_confidence:.2f})"


class ElementMatcher:
    """
    Matches correct element using ML model
    """

    def __init__(self, ml_model_path: Optional[Path] = None):
        """
        Initialize element matcher

        Args:
            ml_model_path: Path to ML model (from Phase 4)
        """
        self.ml_model_path = ml_model_path
        self.ml_model = None

        if ml_model_path and ml_model_path.exists():
            self._load_ml_model()

    def _load_ml_model(self):
        """Load ML model from Phase 4"""
        try:
            from framework.ml.element_classifier import ElementClassifier
            self.ml_model = ElementClassifier()
            self.ml_model.load_model(self.ml_model_path)
        except (ImportError, OSError, ValueError) as e:
            print(f"Warning: Could not load ML model: {e}")
            self.ml_model = None

    def find_best_match(
            self,
            alternatives: List[AlternativeSelector],
            expected_element_type: Optional[str] = None,
            context: Optional[Dict] = None
    ) -> Optional[MatchResult]:
        """
        Find best matching selector from alternatives

        Args:
            alternatives: List of alternative selectors
            expected_element_type: Expected type (button, input, etc.)
            context: Additional context (screen name, nearby elements, etc.)

        Returns:
            Best match or None
        """
        if not alternatives:
            return None

        # Score each alternative
        scored = []
        for alt in alternatives:
            score = self._score_alternative(alt, expected_element_type, context)
            if score:
                scored.append(score)

        # Return highest scoring match
        if scored:
            scored.sort(key=lambda x: x.combined_confidence, reverse=True)
            return scored[0]

        return None

    def _score_alternative(
            self,
            alternative: AlternativeSelector,
            expected_element_type: Optional[str],
            context: Optional[Dict]
    ) -> Optional[MatchResult]:
        """Score a single alternative"""

        # Start with selector's base confidence
        base_confidence = alternative.confidence

        # Get ML confidence if model available
        ml_confidence = 0.0
        if self.ml_model:
            ml_confidence = self._get_ml_confidence(alternative, expected_element_type)

        # Combine confidences (weighted average)
        if ml_confidence > 0:
            combined = (base_confidence * 0.4) + (ml_confidence * 0.6)
        else:
            combined = base_confidence

        # Apply context boosts
        if context:
            combined = self._apply_context_boost(combined, alternative, context)

        reasoning = self._generate_reasoning(
            alternative, base_confidence, ml_confidence, combined
        )

        return MatchResult(
            selector=alternative,
            ml_confidence=ml_confidence,
            combined_confidence=combined,
            reasoning=reasoning
        )

    def _get_ml_confidence(
            self,
            alternative: AlternativeSelector,
            expected_type: Optional[str]
    ) -> float:
        """Get confidence from ML model"""
        if not self.ml_model:
            return 0.0

        try:
            # Prepare features for ML model
            features = self._extract_features(alternative)

            # Get prediction
            prediction = self.ml_model.predict(features)

            # If expected type provided, check if it matches
            if expected_type and prediction['type'] == expected_type:
                return prediction['confidence']
            elif not expected_type:
                return prediction['confidence']
            else:
                # Type mismatch - lower confidence
                return prediction['confidence'] * 0.5

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            print(f"ML prediction error: {e}")
            return 0.0

    def _extract_features(self, alternative: AlternativeSelector) -> Dict:
        """Extract features for ML model"""
        attrs = alternative.element_attributes

        return {
            'class': attrs.get('class', ''),
            'resource_id': attrs.get('resource-id', ''),
            'text': attrs.get('text', ''),
            'content_desc': attrs.get('content-desc', ''),
            'clickable': attrs.get('clickable', 'false') == 'true',
            'enabled': attrs.get('enabled', 'true') == 'true',
            'bounds': attrs.get('bounds', ''),
        }

    def _apply_context_boost(
            self,
            confidence: float,
            alternative: AlternativeSelector,
            context: Dict
    ) -> float:
        """Apply context-based confidence boost"""
        boosted = confidence

        # Boost for matching screen name
        screen_name = context.get('screen_name', '')
        if screen_name:
            class_name = alternative.element_attributes.get('class', '')
            if screen_name.lower() in class_name.lower():
                boosted = min(1.0, boosted + 0.05)

        # Boost for stable selector types
        stable_types = ['id', 'accessibility_id']
        if alternative.strategy.value in stable_types:
            boosted = min(1.0, boosted + 0.05)

        return boosted

    def _generate_reasoning(
            self,
            alternative: AlternativeSelector,
            base_conf: float,
            ml_conf: float,
            combined: float
    ) -> str:
        """Generate human-readable reasoning"""
        reasoning = []

        reasoning.append(f"Strategy: {alternative.strategy.value}")
        reasoning.append(f"Base confidence: {base_conf:.2f}")

        if ml_conf > 0:
            reasoning.append(f"ML confidence: {ml_conf:.2f}")

        reasoning.append(f"Combined: {combined:.2f}")

        # Add key attributes
        attrs = alternative.element_attributes
        if attrs.get('resource-id'):
            reasoning.append(f"Has ID: {attrs['resource-id']}")
        if attrs.get('text'):
            reasoning.append(f"Text: '{attrs['text']}'")

        return " | ".join(reasoning)

    def validate_match(
            self,
            match: MatchResult,
            min_confidence: float = 0.7
    ) -> bool:
        """
        Validate if match is confident enough

        Args:
            match: Match result to validate
            min_confidence: Minimum required confidence

        Returns:
            True if match is valid
        """
        return match.combined_confidence >= min_confidence
