"""
Static Analyzers

Analyzes source code to extract UI structure, navigation, and API definitions.
"""

from framework.analyzers.analysis_result import AnalysisResult
from framework.analyzers.android_analyzer import AndroidAnalyzer
from framework.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult as BaseAnalysisResult
from framework.analyzers.native import (
    SourceComplexity,
    analyze_source_complexity,
    backend_name,
    native_available,
)

__all__ = [
    "AndroidAnalyzer",
    "AnalysisResult",
    "BaseAnalyzer",
    "BaseAnalysisResult",
    "SourceComplexity",
    "analyze_source_complexity",
    "backend_name",
    "native_available",
]
