"""Stateless selector-healing strategies.

Each function builds an alternative selector from an element's context and
returns a HealingResult. They hold no state (the stateful visual strategy and
the healing history stay on the SelectorHealer), so they live here as plain
functions — the strategy catalog, separate from the orchestrator.
"""

from typing import Any, Dict

from framework.ml.healing_types import HealingResult, HealingStrategy
from framework.model.app_model import Selector


def heal_with_text(broken_selector: Selector, context: Dict[str, Any]) -> HealingResult:
    """Heal selector using element text."""
    text = context.get("text")

    if not text:
        return HealingResult(
            success=False,
            original_selector=str(broken_selector),
            healed_selector=None,
            strategy=HealingStrategy.TEXT_BASED,
            confidence=0.0,
            reason="No text available",
        )

    # Generate text-based selector
    platform = context.get("platform", "android")

    if platform == "android":
        healed = f"//android.widget.*[@text='{text}']"
    else:  # iOS
        healed = f"//XCUIElementType*[@label='{text}']"

    confidence = 0.8 if not context.get("text_dynamic") else 0.6

    return HealingResult(
        success=True,
        original_selector=str(broken_selector),
        healed_selector=healed,
        strategy=HealingStrategy.TEXT_BASED,
        confidence=confidence,
        reason=f"Using text-based selector: {text}",
    )


def heal_with_attributes(broken_selector: Selector, context: Dict[str, Any]) -> HealingResult:
    """Heal selector using element attributes."""
    # Collect available attributes
    attributes = []

    if context.get("content_desc"):
        attributes.append(f"@content-desc='{context['content_desc']}'")

    if context.get("class"):
        attributes.append(f"@class='{context['class']}'")

    if context.get("clickable"):
        attributes.append("@clickable='true'")

    if not attributes:
        return HealingResult(
            success=False,
            original_selector=str(broken_selector),
            healed_selector=None,
            strategy=HealingStrategy.ATTRIBUTE_BASED,
            confidence=0.0,
            reason="No attributes available",
        )

    # Build XPath with multiple attributes
    platform = context.get("platform", "android")

    if platform == "android":
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
        reason=f"Using attribute-based selector with {len(attributes)} attributes",
    )


def heal_with_hierarchy(broken_selector: Selector, context: Dict[str, Any]) -> HealingResult:
    """Heal selector using parent/sibling hierarchy."""
    parent = context.get("parent")

    if not parent:
        return HealingResult(
            success=False,
            original_selector=str(broken_selector),
            healed_selector=None,
            strategy=HealingStrategy.HIERARCHY_BASED,
            confidence=0.0,
            reason="No parent information available",
        )

    # Build hierarchy-based selector
    child_text = context.get("text", "")
    parent_class = parent.get("class", "*")

    platform = context.get("platform", "android")

    if platform == "android":
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
        reason="Using parent-child hierarchy",
    )


def heal_with_position(broken_selector: Selector, context: Dict[str, Any]) -> HealingResult:
    """Heal selector using position (fragile)."""
    position = context.get("position")

    if position is None:
        return HealingResult(
            success=False,
            original_selector=str(broken_selector),
            healed_selector=None,
            strategy=HealingStrategy.POSITION_BASED,
            confidence=0.0,
            reason="No position information available",
        )

    # Build position-based selector
    element_class = context.get("class", "*")
    platform = context.get("platform", "android")

    if platform == "android":
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
        reason=f"Using position-based selector (index: {position}) - WARNING: fragile",
    )
