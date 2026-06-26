"""
Selector Scorer

Evaluates selector stability and reliability.
"""

from enum import Enum
from typing import Dict, List


class SelectorStability(str, Enum):
    """Selector stability levels"""
    EXCELLENT = "excellent"  # 0.9-1.0 - ID-based, very stable
    GOOD = "good"  # 0.7-0.9 - Resource ID, accessibility ID
    FAIR = "fair"  # 0.5-0.7 - Text-based, class+index
    POOR = "poor"  # 0.3-0.5 - XPath with multiple levels
    FRAGILE = "fragile"  # 0.0-0.3 - Complex XPath, dynamic attributes


class SelectorScorer:
    """
    Scores selectors based on stability and reliability

    Helps prioritize which selectors to use and when to add fallbacks.
    """

    def __init__(self):
        # Scoring weights for different selector types
        self.type_scores = {
            'test_id': 1.0,  # Best: Developer-provided test IDs
            'accessibility_id': 0.95,  # Excellent: Accessibility identifiers
            'resource_id': 0.90,  # Excellent: Android resource IDs
            'id': 0.90,  # Excellent: iOS view IDs
            'content_desc': 0.75,  # Good: Content descriptions
            'text': 0.60,  # Fair: Visible text (can change)
            'class_name': 0.50,  # Fair: Class + attributes
            'xpath': 0.30,  # Poor: XPath (fragile)
            'index': 0.20  # Fragile: Position-based
        }

    def score_selector(
            self,
            selector: Dict[str, str],
            platform: str = "android"
    ) -> float:
        """
        Score a single selector

        Args:
            selector: Selector dictionary (e.g., {"test_id": "login_button"})
            platform: Target platform

        Returns:
            Score between 0.0 and 1.0
        """
        if not selector:
            return 0.0

        # Get primary strategy
        primary_key = list(selector.keys())[0] if selector else None

        if not primary_key:
            return 0.0

        # Base score from type
        base_score = self.type_scores.get(primary_key, 0.3)

        # Modifiers
        score = base_score

        # Bonus for multiple attributes
        if len(selector) > 1:
            score = min(1.0, score * 1.1)

        # XPath penalty analysis
        if primary_key == 'xpath':
            xpath = selector['xpath']
            score = self._score_xpath(xpath)

        # Text-based penalty for dynamic content
        if primary_key == 'text':
            text = selector['text']
            if self._looks_dynamic(text):
                score *= 0.7

        return round(score, 2)

    def _score_xpath(self, xpath: str) -> float:
        """Score XPath selector quality"""
        score = 0.3  # Base XPath score

        # Penalties
        depth = xpath.count('/')
        if depth > 5:
            score *= 0.7  # Deep nesting is fragile

        if '[' in xpath and ']' in xpath:
            score *= 0.8  # Index-based is position-dependent

        if '*' in xpath:
            score *= 0.9  # Wildcards are less specific

        # Bonuses
        if '@resource-id' in xpath or '@content-desc' in xpath:
            score *= 1.3  # Using attributes is better

        if '@text=' in xpath:
            score *= 0.9  # Text in XPath is fragile

        return min(0.8, score)  # Cap XPath at 0.8

    def _looks_dynamic(self, text: str) -> bool:
        """Check if text looks dynamic (numbers, dates, etc.)"""
        import re

        # Contains numbers
        if re.search(r'\d{2,}', text):
            return True

        # Contains currency
        if any(symbol in text for symbol in ['$', '€', '£', '¥']):
            return True

        # Very short (likely generated)
        if len(text) < 3:
            return True

        return False

    def get_stability_level(self, score: float) -> SelectorStability:
        """Convert score to stability level"""
        if score >= 0.9:
            return SelectorStability.EXCELLENT
        elif score >= 0.7:
            return SelectorStability.GOOD
        elif score >= 0.5:
            return SelectorStability.FAIR
        elif score >= 0.3:
            return SelectorStability.POOR
        else:
            return SelectorStability.FRAGILE

    def recommend_fallbacks(
            self,
            primary_selector: Dict[str, str],
            available_attributes: Dict[str, str]
    ) -> List[Dict[str, str]]:
        """
        Recommend fallback selectors based on available attributes

        Args:
            primary_selector: Primary selector being used
            available_attributes: All available attributes for this element

        Returns:
            List of fallback selectors in priority order
        """
        fallbacks = []

        # Build potential selectors from available attributes
        potential = []

        for attr_key, attr_value in available_attributes.items():
            if not attr_value:
                continue

            selector = {attr_key: attr_value}
            score = self.score_selector(selector)
            potential.append((score, selector))

        # Sort by score (descending)
        potential.sort(key=lambda x: x[0], reverse=True)

        # Take top 3 (excluding primary if present)
        primary_key = list(primary_selector.keys())[0] if primary_selector else None

        for score, selector in potential:
            selector_key = list(selector.keys())[0]

            # Skip if it's the primary selector
            if selector_key == primary_key:
                continue

            # Only add if score is reasonable
            if score >= 0.5:
                fallbacks.append(selector)

            if len(fallbacks) >= 3:
                break

        return fallbacks
