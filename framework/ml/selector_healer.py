"""
Selector healing engine for self-healing test scripts.

Automatically detects broken selectors and generates alternative strategies.

This module was decomposed by responsibility: the shared value types live in
:mod:`framework.ml.healing_types`, the stateless strategy builders in
:mod:`framework.ml.healing_strategies`, and the fallback-usage/Page-Object
auto-update behaviour in :mod:`framework.ml.fallback_tracker` (inherited here).
``HealingStrategy`` and ``HealingResult`` are re-exported so existing imports
(``from framework.ml.selector_healer import ...``) keep working.
"""

import logging
from typing import Any, Dict, List, Optional

from framework.ml.fallback_tracker import FallbackTracker
from framework.ml.healing_strategies import (
    heal_with_attributes,
    heal_with_hierarchy,
    heal_with_position,
    heal_with_text,
)
from framework.ml.healing_types import HealingResult, HealingStrategy
from framework.model.app_model import Selector

logger = logging.getLogger(__name__)

__all__ = ["HealingStrategy", "HealingResult", "SelectorHealer"]


class SelectorHealer(FallbackTracker):
    """
    Self-healing selector engine.

    Features:
    - Detect broken selectors
    - Generate alternative selectors
    - Track selector evolution
    - Auto-repair test scripts
    """

    def __init__(self):
        """Initialize selector healer."""
        super().__init__()
        self.healing_history: List[HealingResult] = []
        self.healing_stats: Dict[str, Any] = {
            "total_healed": 0,
            "successful": 0,
            "failed": 0,
            "by_strategy": {},
            # visual-based healing increments its own counters in
            # _heal_with_visual; must exist up front or every visual heal raises
            # KeyError (which the broad handler swallows -> heal silently lost).
            "visual_based": {"successes": 0, "failures": 0},
        }

    def detect_broken_selector(self, selector: Selector, execution_result: Dict[str, Any]) -> bool:
        """
        Detect if selector is broken based on execution result.

        Args:
            selector: Selector to check
            execution_result: Result from test execution

        Returns:
            True if selector is broken
        """
        # Check for common failure indicators
        if execution_result.get("element_not_found"):
            return True

        if execution_result.get("timeout"):
            return True

        if execution_result.get("stale_element"):
            return True

        return False

    def heal_selector(
        self,
        broken_selector: Selector,
        element_context: Dict[str, Any],
        available_strategies: Optional[List[HealingStrategy]] = None,
    ) -> HealingResult:
        """
        Attempt to heal broken selector.

        Args:
            broken_selector: Selector that failed
            element_context: Context about the element (text, position, etc.)
            available_strategies: Strategies to try (default: all)

        Returns:
            HealingResult with healed selector or failure reason
        """
        if available_strategies is None:
            available_strategies = list(HealingStrategy)

        # Try each strategy in order of preference
        for strategy in self._prioritize_strategies(available_strategies, element_context):
            result = self._try_healing_strategy(broken_selector, element_context, strategy)

            if result.success:
                self.healing_history.append(result)
                logger.info(f"Selector healed using {strategy}: {result.healed_selector}")
                return result

        # All strategies failed
        failed_result = HealingResult(
            success=False,
            original_selector=str(broken_selector),
            healed_selector=None,
            strategy=None,
            confidence=0.0,
            reason="All healing strategies failed",
        )

        self.healing_history.append(failed_result)
        return failed_result

    def _prioritize_strategies(
        self, strategies: List[HealingStrategy], context: Dict[str, Any]
    ) -> List[HealingStrategy]:
        """
        Prioritize healing strategies based on available context.

        Args:
            strategies: Available strategies
            context: Element context

        Returns:
            Prioritized list of strategies
        """
        priorities = []

        for strategy in strategies:
            priority = 0

            if strategy == HealingStrategy.TEXT_BASED:
                # High priority if element has stable text
                if context.get("text") and not context.get("text_dynamic"):
                    priority = 90
                elif context.get("text"):
                    priority = 70

            elif strategy == HealingStrategy.ATTRIBUTE_BASED:
                # High priority if element has multiple attributes
                attr_count = sum([1 for key in ["content_desc", "class", "enabled", "clickable"] if context.get(key)])
                priority = 60 + (attr_count * 5)

            elif strategy == HealingStrategy.HIERARCHY_BASED:
                # Medium priority if parent/sibling info available
                if context.get("parent") or context.get("siblings"):
                    priority = 50

            elif strategy == HealingStrategy.POSITION_BASED:
                # Lower priority (fragile)
                if context.get("position"):
                    priority = 30

            elif strategy == HealingStrategy.VISUAL_BASED:
                # Lowest priority (requires screenshot)
                if context.get("screenshot"):
                    priority = 20

            priorities.append((priority, strategy))

        # Sort by priority (descending)
        priorities.sort(key=lambda x: x[0], reverse=True)

        return [strategy for _, strategy in priorities]

    def _try_healing_strategy(
        self, broken_selector: Selector, context: Dict[str, Any], strategy: HealingStrategy
    ) -> HealingResult:
        """Dispatch to a specific healing strategy.

        The stateless builders live in :mod:`framework.ml.healing_strategies`;
        visual healing stays here as it updates ``healing_stats``.
        """
        if strategy == HealingStrategy.TEXT_BASED:
            return heal_with_text(broken_selector, context)
        elif strategy == HealingStrategy.ATTRIBUTE_BASED:
            return heal_with_attributes(broken_selector, context)
        elif strategy == HealingStrategy.HIERARCHY_BASED:
            return heal_with_hierarchy(broken_selector, context)
        elif strategy == HealingStrategy.POSITION_BASED:
            return heal_with_position(broken_selector, context)
        elif strategy == HealingStrategy.VISUAL_BASED:
            return self._heal_with_visual(broken_selector, context)
        else:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=strategy,
                confidence=0.0,
                reason=f"Unknown strategy: {strategy}",
            )

    def _heal_with_visual(self, broken_selector: Selector, context: Dict[str, Any]) -> HealingResult:
        """Heal selector using visual recognition (requires screenshot)."""
        screenshot = context.get("screenshot")

        if not screenshot:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.VISUAL_BASED,
                confidence=0.0,
                reason="No screenshot available",
            )

        try:
            from framework.ml.visual_detector import VisualDetector
            from pathlib import Path

            # Initialize visual detector
            visual_detector = VisualDetector()

            # Get element bounds from selector context
            bounds = context.get("bounds")
            if not bounds:
                return HealingResult(
                    success=False,
                    original_selector=str(broken_selector),
                    healed_selector=None,
                    strategy=HealingStrategy.VISUAL_BASED,
                    confidence=0.0,
                    reason="No element bounds in context",
                )

            # Try to find element by visual similarity
            screenshot_path = Path(screenshot)
            if not screenshot_path.exists():
                return HealingResult(
                    success=False,
                    original_selector=str(broken_selector),
                    healed_selector=None,
                    strategy=HealingStrategy.VISUAL_BASED,
                    confidence=0.0,
                    reason=f"Screenshot not found: {screenshot}",
                )

            # Extract element region from original bounds
            x, y, width, height = bounds["x"], bounds["y"], bounds["width"], bounds["height"]

            # Find similar elements in current screenshot
            matches = visual_detector.find_similar_by_bounds(
                screenshot_path, target_bounds=(x, y, width, height), similarity_threshold=0.8
            )

            if matches:
                # Use the best match (highest similarity)
                best_match = max(matches, key=lambda m: m["similarity"])

                # Generate new selector based on best match position
                new_selector = f"visual_position:{best_match['x']},{best_match['y']}"

                self.healing_stats["visual_based"]["successes"] += 1

                return HealingResult(
                    success=True,
                    original_selector=str(broken_selector),
                    healed_selector=new_selector,
                    strategy=HealingStrategy.VISUAL_BASED,
                    confidence=best_match["similarity"],
                    reason=f"Found visually similar element at ({best_match['x']}, {best_match['y']})",
                )
            else:
                self.healing_stats["visual_based"]["failures"] += 1

                return HealingResult(
                    success=False,
                    original_selector=str(broken_selector),
                    healed_selector=None,
                    strategy=HealingStrategy.VISUAL_BASED,
                    confidence=0.0,
                    reason="No visually similar elements found",
                )

        except ImportError:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.VISUAL_BASED,
                confidence=0.0,
                reason="VisualDetector not available",
            )
        except (ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Visual-based healing failed: {e}")
            self.healing_stats["visual_based"]["failures"] += 1

            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.VISUAL_BASED,
                confidence=0.0,
                reason=f"Visual healing error: {str(e)}",
            )

    def get_healing_stats(self) -> Dict[str, Any]:
        """Get statistics about healing attempts."""
        if not self.healing_history:
            return {"total_attempts": 0, "successful": 0, "failed": 0, "success_rate": 0.0, "strategies": {}}

        total = len(self.healing_history)
        successful = sum(1 for r in self.healing_history if r.success)

        # Count by strategy
        strategy_counts = {}
        for result in self.healing_history:
            if result.strategy:
                strategy = result.strategy.value
                if strategy not in strategy_counts:
                    strategy_counts[strategy] = {"attempts": 0, "successes": 0}

                strategy_counts[strategy]["attempts"] += 1
                if result.success:
                    strategy_counts[strategy]["successes"] += 1

        return {
            "total_attempts": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total if total > 0 else 0.0,
            "strategies": strategy_counts,
        }
