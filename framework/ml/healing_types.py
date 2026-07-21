"""Shared value types for the selector-healing engine.

Extracted from selector_healer.py so the healer, the stateless strategy
builders, and any caller can share them without a circular import.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


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
