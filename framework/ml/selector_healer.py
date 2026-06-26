"""
Selector healing engine for self-healing test scripts.

Automatically detects broken selectors and generates alternative strategies.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any

from framework.model.app_model import Selector

logger = logging.getLogger(__name__)


class HealingStrategy(str, Enum):
    """Selector healing strategies."""
    TEXT_BASED = "text_based"
    POSITION_BASED = "position_based"
    HIERARCHY_BASED = "hierarchy_based"
    VISUAL_BASED = "visual_based"
    ATTRIBUTE_BASED = "attribute_based"


@dataclass
class HealingResult:
    """Result of selector healing attempt."""
    success: bool
    original_selector: str
    healed_selector: Optional[str]
    strategy: Optional[HealingStrategy]
    confidence: float
    reason: str


class SelectorHealer:
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
        self.healing_history: List[HealingResult] = []
        self.fallback_reports: List[Dict[str, Any]] = []
        self.page_object_updates: List[Dict[str, Any]] = []
        self.healing_stats: Dict[str, Any] = {
            "total_healed": 0,
            "successful": 0,
            "failed": 0,
            "by_strategy": {}
        }

    def report_fallback_usage(
            self,
            element_name: str,
            page_object_file: str,
            primary_selector: str,
            successful_fallback: str,
            fallback_index: int,
            platform: str
    ) -> None:
        """
        Report that a fallback selector was used successfully.

        This is called from Page Object _find_element_with_fallback() method
        when a fallback selector succeeds after primary fails.

        Args:
            element_name: Name of the element (e.g., 'login_button')
            page_object_file: Path to Page Object file
            primary_selector: The selector that failed
            successful_fallback: The fallback selector that succeeded
            fallback_index: Index of fallback (0-based)
            platform: 'android' or 'ios'
        """
        report = {
            'timestamp': self._get_timestamp(),
            'element_name': element_name,
            'page_object_file': page_object_file,
            'primary_selector': primary_selector,
            'successful_fallback': successful_fallback,
            'fallback_index': fallback_index,
            'platform': platform
        }

        self.fallback_reports.append(report)

        logger.info(
            f"[SelectorHealer] Fallback reported: {element_name} in {page_object_file}\n"
            f"  Failed: {primary_selector}\n"
            f"  Succeeded: {successful_fallback} (fallback #{fallback_index + 1})"
        )

        # Auto-update Page Object if threshold reached
        if self._should_auto_update(element_name, page_object_file):
            self.update_page_object(page_object_file, element_name, successful_fallback, platform)

    def _should_auto_update(self, element_name: str, page_object_file: str) -> bool:
        """
        Determine if Page Object should be auto-updated.

        Auto-update if:
        - Same element failed 3+ times
        - Same fallback succeeded 3+ times
        """
        # Count failures for this element in this file
        failures = [
            r for r in self.fallback_reports
            if r['element_name'] == element_name and r['page_object_file'] == page_object_file
        ]

        if len(failures) < 3:
            return False

        # Check if same fallback succeeded multiple times
        recent_failures = failures[-5:]  # Last 5 failures
        fallback_counts = {}

        for failure in recent_failures:
            fallback = failure['successful_fallback']
            fallback_counts[fallback] = fallback_counts.get(fallback, 0) + 1

        # If any fallback succeeded 3+ times, auto-update
        return any(count >= 3 for count in fallback_counts.values())

    def update_page_object(
            self,
            page_object_file: str,
            element_name: str,
            new_primary_selector: str,
            platform: str
    ) -> bool:
        """
        Update Page Object file with new primary selector.

        Args:
            page_object_file: Path to Page Object file
            element_name: Element to update
            new_primary_selector: New selector to promote to primary
            platform: 'android' or 'ios'

        Returns:
            True if update successful
        """
        from pathlib import Path
        import re

        page_path = Path(page_object_file)

        if not page_path.exists():
            logger.error(f"[SelectorHealer] Page Object not found: {page_object_file}")
            return False

        try:
            # Read current Page Object
            content = page_path.read_text()

            # Find selector dictionary for this element
            selector_name = f"{element_name.upper()}_SELECTOR"

            # Pattern to match selector dictionary
            pattern = rf'({selector_name}\s*=\s*\{{[^}}]+"{platform}"\s*:\s*)"([^"]+)"'

            # Replace with new selector
            def replace_selector(match):
                prefix = match.group(1)
                old_selector = match.group(2)

                logger.info(
                    f"[SelectorHealer] Updating {element_name} in {page_object_file}\n"
                    f"  Old ({platform}): {old_selector}\n"
                    f"  New ({platform}): {new_primary_selector}"
                )

                return f'{prefix}"{new_primary_selector}"'

            updated_content = re.sub(pattern, replace_selector, content, count=1)

            if updated_content == content:
                logger.warning(
                    f"[SelectorHealer] Selector not found for update: {selector_name} ({platform})"
                )
                return False

            # Backup original file
            backup_path = page_path.with_suffix('.py.bak')
            page_path.rename(backup_path)

            # Write updated content
            page_path.write_text(updated_content)

            # Record update
            update_record = {
                'timestamp': self._get_timestamp(),
                'page_object_file': page_object_file,
                'element_name': element_name,
                'platform': platform,
                'new_primary_selector': new_primary_selector,
                'backup_file': str(backup_path)
            }

            self.page_object_updates.append(update_record)

            logger.info(
                "[SelectorHealer] Page Object updated successfully!\n"
                f"  File: {page_object_file}\n"
                f"  Element: {element_name}\n"
                f"  Platform: {platform}\n"
                f"  New selector: {new_primary_selector}\n"
                f"  Backup: {backup_path}"
            )

            return True

        except (OSError, re.error, UnicodeDecodeError, ValueError) as e:
            logger.error(f"[SelectorHealer] Failed to update Page Object: {e}")
            return False

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime
        return datetime.now().isoformat()

    def get_fallback_stats(self) -> Dict[str, Any]:
        """Get statistics about fallback usage."""
        if not self.fallback_reports:
            return {
                'total_fallbacks': 0,
                'unique_elements': 0,
                'unique_page_objects': 0,
                'auto_updates': len(self.page_object_updates),
                'by_platform': {}
            }

        # Count unique elements and files
        unique_elements = set(r['element_name'] for r in self.fallback_reports)
        unique_files = set(r['page_object_file'] for r in self.fallback_reports)

        # Count by platform
        by_platform = {}
        for report in self.fallback_reports:
            platform = report['platform']
            if platform not in by_platform:
                by_platform[platform] = 0
            by_platform[platform] += 1

        return {
            'total_fallbacks': len(self.fallback_reports),
            'unique_elements': len(unique_elements),
            'unique_page_objects': len(unique_files),
            'auto_updates': len(self.page_object_updates),
            'by_platform': by_platform
        }

    def detect_broken_selector(
            self,
            selector: Selector,
            execution_result: Dict[str, Any]
    ) -> bool:
        """
        Detect if selector is broken based on execution result.

        Args:
            selector: Selector to check
            execution_result: Result from test execution

        Returns:
            True if selector is broken
        """
        # Check for common failure indicators
        if execution_result.get('element_not_found'):
            return True

        if execution_result.get('timeout'):
            return True

        if execution_result.get('stale_element'):
            return True

        return False

    def heal_selector(
            self,
            broken_selector: Selector,
            element_context: Dict[str, Any],
            available_strategies: Optional[List[HealingStrategy]] = None
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
            reason="All healing strategies failed"
        )

        self.healing_history.append(failed_result)
        return failed_result

    def _prioritize_strategies(
            self,
            strategies: List[HealingStrategy],
            context: Dict[str, Any]
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
                if context.get('text') and not context.get('text_dynamic'):
                    priority = 90
                elif context.get('text'):
                    priority = 70

            elif strategy == HealingStrategy.ATTRIBUTE_BASED:
                # High priority if element has multiple attributes
                attr_count = sum([
                    1 for key in ['content_desc', 'class', 'enabled', 'clickable']
                    if context.get(key)
                ])
                priority = 60 + (attr_count * 5)

            elif strategy == HealingStrategy.HIERARCHY_BASED:
                # Medium priority if parent/sibling info available
                if context.get('parent') or context.get('siblings'):
                    priority = 50

            elif strategy == HealingStrategy.POSITION_BASED:
                # Lower priority (fragile)
                if context.get('position'):
                    priority = 30

            elif strategy == HealingStrategy.VISUAL_BASED:
                # Lowest priority (requires screenshot)
                if context.get('screenshot'):
                    priority = 20

            priorities.append((priority, strategy))

        # Sort by priority (descending)
        priorities.sort(key=lambda x: x[0], reverse=True)

        return [strategy for _, strategy in priorities]

    def _try_healing_strategy(
            self,
            broken_selector: Selector,
            context: Dict[str, Any],
            strategy: HealingStrategy
    ) -> HealingResult:
        """Try specific healing strategy."""

        if strategy == HealingStrategy.TEXT_BASED:
            return self._heal_with_text(broken_selector, context)

        elif strategy == HealingStrategy.ATTRIBUTE_BASED:
            return self._heal_with_attributes(broken_selector, context)

        elif strategy == HealingStrategy.HIERARCHY_BASED:
            return self._heal_with_hierarchy(broken_selector, context)

        elif strategy == HealingStrategy.POSITION_BASED:
            return self._heal_with_position(broken_selector, context)

        elif strategy == HealingStrategy.VISUAL_BASED:
            return self._heal_with_visual(broken_selector, context)

        else:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=strategy,
                confidence=0.0,
                reason=f"Unknown strategy: {strategy}"
            )

    def _heal_with_text(
            self,
            broken_selector: Selector,
            context: Dict[str, Any]
    ) -> HealingResult:
        """Heal selector using element text."""
        text = context.get('text')

        if not text:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.TEXT_BASED,
                confidence=0.0,
                reason="No text available"
            )

        # Generate text-based selector
        platform = context.get('platform', 'android')

        if platform == 'android':
            healed = f"//android.widget.*[@text='{text}']"
        else:  # iOS
            healed = f"//XCUIElementType*[@label='{text}']"

        confidence = 0.8 if not context.get('text_dynamic') else 0.6

        return HealingResult(
            success=True,
            original_selector=str(broken_selector),
            healed_selector=healed,
            strategy=HealingStrategy.TEXT_BASED,
            confidence=confidence,
            reason=f"Using text-based selector: {text}"
        )

    def _heal_with_attributes(
            self,
            broken_selector: Selector,
            context: Dict[str, Any]
    ) -> HealingResult:
        """Heal selector using element attributes."""
        # Collect available attributes
        attributes = []

        if context.get('content_desc'):
            attributes.append(f"@content-desc='{context['content_desc']}'")

        if context.get('class'):
            attributes.append(f"@class='{context['class']}'")

        if context.get('clickable'):
            attributes.append("@clickable='true'")

        if not attributes:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.ATTRIBUTE_BASED,
                confidence=0.0,
                reason="No attributes available"
            )

        # Build XPath with multiple attributes
        platform = context.get('platform', 'android')

        if platform == 'android':
            healed = f"//android.widget.*[{' and '.join(attributes)}]"
        else:
            healed = f"//XCUIElementType*[{' and '.join(attributes)}]"

        confidence = 0.75

        return HealingResult(
            success=True,
            original_selector=str(broken_selector),
            healed_selector=healed,
            strategy=HealingStrategy.ATTRIBUTE_BASED,
            confidence=confidence,
            reason=f"Using attribute-based selector with {len(attributes)} attributes"
        )

    def _heal_with_hierarchy(
            self,
            broken_selector: Selector,
            context: Dict[str, Any]
    ) -> HealingResult:
        """Heal selector using parent/sibling hierarchy."""
        parent = context.get('parent')

        if not parent:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.HIERARCHY_BASED,
                confidence=0.0,
                reason="No parent information available"
            )

        # Build hierarchy-based selector
        child_text = context.get('text', '')
        parent_class = parent.get('class', '*')

        platform = context.get('platform', 'android')

        if platform == 'android':
            if child_text:
                healed = f"//{parent_class}/*[@text='{child_text}']"
            else:
                healed = f"//{parent_class}/*[@clickable='true']"
        else:
            if child_text:
                healed = f"//{parent_class}/*[@label='{child_text}']"
            else:
                healed = f"//{parent_class}/*[@enabled='true']"

        confidence = 0.65

        return HealingResult(
            success=True,
            original_selector=str(broken_selector),
            healed_selector=healed,
            strategy=HealingStrategy.HIERARCHY_BASED,
            confidence=confidence,
            reason="Using parent-child hierarchy"
        )

    def _heal_with_position(
            self,
            broken_selector: Selector,
            context: Dict[str, Any]
    ) -> HealingResult:
        """Heal selector using position (fragile)."""
        position = context.get('position')

        if position is None:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.POSITION_BASED,
                confidence=0.0,
                reason="No position information available"
            )

        # Build position-based selector
        element_class = context.get('class', '*')
        platform = context.get('platform', 'android')

        if platform == 'android':
            healed = f"(//{element_class})[{position + 1}]"
        else:
            healed = f"(//{element_class})[{position + 1}]"

        # Low confidence (position is fragile)
        confidence = 0.4

        return HealingResult(
            success=True,
            original_selector=str(broken_selector),
            healed_selector=healed,
            strategy=HealingStrategy.POSITION_BASED,
            confidence=confidence,
            reason=f"Using position-based selector (index: {position}) - WARNING: fragile"
        )

    def _heal_with_visual(
            self,
            broken_selector: Selector,
            context: Dict[str, Any]
    ) -> HealingResult:
        """Heal selector using visual recognition (requires screenshot)."""
        screenshot = context.get('screenshot')

        if not screenshot:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.VISUAL_BASED,
                confidence=0.0,
                reason="No screenshot available"
            )

        try:
            from framework.ml.visual_detector import VisualDetector
            from pathlib import Path

            # Initialize visual detector
            visual_detector = VisualDetector()

            # Get element bounds from selector context
            bounds = context.get('bounds')
            if not bounds:
                return HealingResult(
                    success=False,
                    original_selector=str(broken_selector),
                    healed_selector=None,
                    strategy=HealingStrategy.VISUAL_BASED,
                    confidence=0.0,
                    reason="No element bounds in context"
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
                    reason=f"Screenshot not found: {screenshot}"
                )

            # Extract element region from original bounds
            x, y, width, height = bounds['x'], bounds['y'], bounds['width'], bounds['height']

            # Find similar elements in current screenshot
            matches = visual_detector.find_similar_by_bounds(
                screenshot_path,
                target_bounds=(x, y, width, height),
                similarity_threshold=0.8
            )

            if matches:
                # Use the best match (highest similarity)
                best_match = max(matches, key=lambda m: m['similarity'])

                # Generate new selector based on best match position
                new_selector = f"visual_position:{best_match['x']},{best_match['y']}"

                self.healing_stats['visual_based']['successes'] += 1

                return HealingResult(
                    success=True,
                    original_selector=str(broken_selector),
                    healed_selector=new_selector,
                    strategy=HealingStrategy.VISUAL_BASED,
                    confidence=best_match['similarity'],
                    reason=f"Found visually similar element at ({best_match['x']}, {best_match['y']})"
                )
            else:
                self.healing_stats['visual_based']['failures'] += 1

                return HealingResult(
                    success=False,
                    original_selector=str(broken_selector),
                    healed_selector=None,
                    strategy=HealingStrategy.VISUAL_BASED,
                    confidence=0.0,
                    reason="No visually similar elements found"
                )

        except ImportError:
            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.VISUAL_BASED,
                confidence=0.0,
                reason="VisualDetector not available"
            )
        except (ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Visual-based healing failed: {e}")
            self.healing_stats['visual_based']['failures'] += 1

            return HealingResult(
                success=False,
                original_selector=str(broken_selector),
                healed_selector=None,
                strategy=HealingStrategy.VISUAL_BASED,
                confidence=0.0,
                reason=f"Visual healing error: {str(e)}"
            )

    def get_healing_stats(self) -> Dict[str, Any]:
        """Get statistics about healing attempts."""
        if not self.healing_history:
            return {
                'total_attempts': 0,
                'successful': 0,
                'failed': 0,
                'success_rate': 0.0,
                'strategies': {}
            }

        total = len(self.healing_history)
        successful = sum(1 for r in self.healing_history if r.success)

        # Count by strategy
        strategy_counts = {}
        for result in self.healing_history:
            if result.strategy:
                strategy = result.strategy.value
                if strategy not in strategy_counts:
                    strategy_counts[strategy] = {'attempts': 0, 'successes': 0}

                strategy_counts[strategy]['attempts'] += 1
                if result.success:
                    strategy_counts[strategy]['successes'] += 1

        return {
            'total_attempts': total,
            'successful': successful,
            'failed': total - successful,
            'success_rate': successful / total if total > 0 else 0.0,
            'strategies': strategy_counts
        }
