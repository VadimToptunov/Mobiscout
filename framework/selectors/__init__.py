"""
Advanced Selector Strategies

Provides intelligent selector generation and optimization.
"""

from framework.selectors.advanced_selector import (
    AdvancedSelector,
    AdvancedSelectorEngine,
    SelectorBuilder,
    SelectorType,
    FilterOperator,
    SelectorFilter,
    by_id,
    by_text,
    by_class,
    contains_text,
)
from framework.selectors.selector_builder import SelectorBuilder as LegacySelectorBuilder
from framework.selectors.selector_optimizer import SelectorOptimizer
from framework.selectors.selector_scorer import SelectorScorer

__all__ = [
    "SelectorOptimizer",
    "SelectorScorer",
    "LegacySelectorBuilder",
    "SelectorBuilder",
    "AdvancedSelector",
    "AdvancedSelectorEngine",
    "SelectorType",
    "FilterOperator",
    "SelectorFilter",
    "by_id",
    "by_text",
    "by_class",
    "contains_text",
]
