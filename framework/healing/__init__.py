"""
Self-healing test system

Automatically detects and fixes broken selectors when tests fail.
"""

from .element_matcher import ElementMatcher, MatchResult
from .failure_analyzer import FailureAnalyzer, SelectorFailure
from .file_updater import FileUpdater, UpdateResult
from .git_integration import GitIntegration, GitCommitInfo
from .selector_discovery import SelectorDiscovery, AlternativeSelector

__all__ = [
    'FailureAnalyzer',
    'SelectorFailure',
    'SelectorDiscovery',
    'AlternativeSelector',
    'ElementMatcher',
    'MatchResult',
    'FileUpdater',
    'UpdateResult',
    'GitIntegration',
    'GitCommitInfo',
]
