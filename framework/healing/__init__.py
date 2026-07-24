"""
Self-healing test system

Automatically detects and fixes broken selectors when tests fail.
"""

from .element_matcher import ElementMatcher, MatchResult
from .failure_analyzer import FailureAnalyzer, SelectorFailure
from .fallback_tracker import FallbackTracker
from .file_updater import FileUpdater, UpdateResult
from .git_integration import GitIntegration, GitCommitInfo
from .healing_strategies import heal_with_attributes, heal_with_hierarchy, heal_with_position, heal_with_text
from .healing_types import HealingResult, HealingStrategy
from .selector_discovery import SelectorDiscovery, AlternativeSelector

__all__ = [
    "FailureAnalyzer",
    "SelectorFailure",
    "SelectorDiscovery",
    "AlternativeSelector",
    "ElementMatcher",
    "MatchResult",
    "FileUpdater",
    "UpdateResult",
    "GitIntegration",
    "GitCommitInfo",
    # Selector-healing helpers relocated from framework.ml (stateless strategies
    # that build a fresh selector from a known element's attributes, plus the
    # fallback-promotion tracker). Not yet wired into HealingOrchestrator — see
    # docs/CODE_REVIEW.md: they are selector-*generation* from attributes, a
    # different shape from the orchestrator's blind page-source rediscovery.
    "FallbackTracker",
    "HealingResult",
    "HealingStrategy",
    "heal_with_text",
    "heal_with_attributes",
    "heal_with_hierarchy",
    "heal_with_position",
]
