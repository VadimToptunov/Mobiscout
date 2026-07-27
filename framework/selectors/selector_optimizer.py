"""
Selector Optimizer

Optimizes and improves existing selectors.
"""

import re
from typing import Any, Dict, List, Tuple

from framework.model.app_model import Selector, SelectorStability as ModelStability


class SelectorOptimizer:
    """
    Optimizes selectors for better stability and performance

    Analyzes existing selectors and suggests improvements.
    """

    def __init__(self) -> None:
        pass

    def optimize_selector(self, selector: Selector) -> Selector:
        """
        Optimize a selector

        Args:
            selector: Selector to optimize

        Returns:
            Optimized selector
        """
        # Optimize XPath if present in selector
        if selector.xpath:
            optimized_xpath = self._optimize_xpath(selector.xpath)
            if optimized_xpath != selector.xpath:
                selector.xpath = optimized_xpath

        return selector

    def _optimize_xpath(self, xpath: str) -> str:
        """Optimize an XPath expression — conservatively, without changing which
        element it matches.

        The only safe simplification is dropping a *trailing* positional ``[1]``:
        the default "first match" that Appium/Selenium already return, so
        ``//a/b/c/d/e[1]`` -> ``//a/b/c/d/e`` and ``//a/b[@x='y'][1]`` ->
        ``//a/b[@x='y']`` locate the same node. We deliberately do NOT:

        * truncate a deep path to its last couple of segments (``//a/b/c/d`` ->
          ``//c/d``) — that broadens the locator to a different, usually larger
          node-set and silently matches the wrong element; and
        * blanket-``replace("[1]", "")`` — that corrupts multi-digit indices
          (``[10]`` -> ``0]``) and strips meaningful mid-path predicates.

        The ``\\[1\\]$`` pattern matches only a standalone ``[1]`` that is the whole
        final predicate: it never touches ``[10]``/``[12]`` or a ``[1]`` that sits
        mid-path (``//div[1]/span`` is left untouched)."""
        if not xpath:
            return xpath
        return re.sub(r"\[1\]$", "", xpath)

    def analyze_selectors(self, selectors: List[Selector]) -> Dict[str, Any]:
        """
        Analyze a collection of selectors

        Args:
            selectors: List of selectors to analyze

        Returns:
            Analysis report with statistics and recommendations
        """
        total = len(selectors)

        if total == 0:
            return {"total": 0, "statistics": {}, "recommendations": []}

        # Count by stability (using app_model SelectorStability)
        high = sum(1 for s in selectors if s.stability == ModelStability.HIGH)
        medium = sum(1 for s in selectors if s.stability == ModelStability.MEDIUM)
        low = sum(1 for s in selectors if s.stability == ModelStability.LOW)
        unknown = sum(1 for s in selectors if s.stability == ModelStability.UNKNOWN)

        # Count by primary selector type
        strategies: Dict[str, int] = {}
        for selector in selectors:
            # Determine primary strategy from what's set
            if selector.test_id:
                strategy = "test_id"
            elif selector.android and "id:" in selector.android:
                strategy = "resource_id"
            elif selector.ios and "accessibility id:" in selector.ios:
                strategy = "accessibility_id"
            elif selector.xpath:
                strategy = "xpath"
            else:
                strategy = "other"

            strategies[strategy] = strategies.get(strategy, 0) + 1

        # Calculate average stability (map to numeric)
        stability_map = {
            ModelStability.HIGH: 0.9,
            ModelStability.MEDIUM: 0.6,
            ModelStability.LOW: 0.3,
            ModelStability.UNKNOWN: 0.0,
        }
        avg_score = sum(stability_map.get(s.stability, 0) for s in selectors) / total if total > 0 else 0

        # Generate recommendations
        recommendations = []

        if low > total * 0.2:
            recommendations.append(
                f"  {low} low-stability selectors detected ({low / total * 100:.1f}%). "
                "Add test tags or accessibility IDs to improve stability."
            )

        if low + unknown > total * 0.3:
            recommendations.append(
                f"  {low + unknown} unstable selectors ({(low + unknown) / total * 100:.1f}%). "
                "Consider using test IDs, resource IDs, or accessibility IDs."
            )

        xpath_count = strategies.get("xpath", 0)
        if xpath_count > total * 0.5:
            recommendations.append(
                f"  {xpath_count} XPath selectors ({xpath_count / total * 100:.1f}%). "
                "XPath is fragile. Add stable IDs to UI elements."
            )

        if avg_score >= 0.8:
            recommendations.append(f" Good selector quality! Average stability: {avg_score:.2f}")

        return {
            "total": total,
            "average_stability": round(avg_score, 2),
            "stability_distribution": {
                "excellent": high,  # Map HIGH to excellent for display
                "good": medium,  # Map MEDIUM to good
                "fair": 0,  # Not used (kept for compatibility)
                "poor": low,  # Map LOW to poor
                "fragile": unknown,  # Map UNKNOWN to fragile
            },
            "strategy_distribution": strategies,
            "recommendations": recommendations,
        }

    def find_duplicate_selectors(self, selectors: List[Selector]) -> List[Tuple[int, int]]:
        """
        Find duplicate selectors (same selector for different elements)

        Args:
            selectors: List of selectors

        Returns:
            List of (element_id1, element_id2) tuples with duplicate selectors
        """
        duplicates = []
        seen: Dict[str, int] = {}

        for i, selector in enumerate(selectors):
            # Use selector string as key
            if selector.android:
                key = selector.android
                if key in seen:
                    duplicates.append((seen[key], i))
                else:
                    seen[key] = i

            if selector.ios:
                key = selector.ios
                if key in seen:
                    duplicates.append((seen[key], i))
                else:
                    seen[key] = i

        return duplicates

    def suggest_improvements(self, selector: Selector) -> List[str]:
        """
        Suggest improvements for a selector

        Args:
            selector: Selector to analyze

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Check stability
        if selector.stability == ModelStability.LOW or selector.stability == ModelStability.UNKNOWN:
            suggestions.append("  Low stability. Add test tags or accessibility IDs to UI elements.")

        # Check if using XPath
        if selector.xpath:
            suggestions.append(" Using XPath. Consider adding resource-id or test tag for better stability.")

        # Check if using text
        if selector.android and "text:" in selector.android:
            suggestions.append("  Text-based selector. May break if content changes or is localized.")

        # Check if missing iOS selector
        if selector.android and not selector.ios:
            suggestions.append(" Missing iOS selector. Add for cross-platform support.")

        # Check fallback strategies
        total_fallbacks = len(selector.android_fallback) + len(selector.ios_fallback)
        if total_fallbacks < 2:
            suggestions.append(" Add more fallback strategies for resilience.")

        if not suggestions:
            suggestions.append(" Selector looks good!")

        return suggestions
