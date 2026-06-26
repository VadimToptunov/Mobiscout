"""
Base Analyzer Module

Provides abstract base class for all analyzers in the framework.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar('T')


@dataclass
class AnalysisResult(Generic[T]):
    """
    Generic result container for analysis operations.

    Attributes:
        findings: List of analysis findings (type depends on analyzer)
        metadata: Additional metadata about the analysis
        duration_ms: Time taken for analysis in milliseconds
        success: Whether the analysis completed successfully
        errors: List of errors encountered during analysis
    """
    findings: List[T] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    success: bool = True
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            'findings': [
                f.to_dict() if hasattr(f, 'to_dict') else f
                for f in self.findings
            ],
            'metadata': self.metadata,
            'duration_ms': self.duration_ms,
            'success': self.success,
            'errors': self.errors,
        }


class BaseAnalyzer(ABC, Generic[T]):
    """
    Abstract base class for all analyzers.

    Provides common functionality for:
    - Logging setup
    - Timing measurements
    - Safe file reading
    - Result generation

    Subclasses must implement the `analyze` method.

    Example:
        class SecurityAnalyzer(BaseAnalyzer[SecurityFinding]):
            def analyze(self, **kwargs) -> AnalysisResult[SecurityFinding]:
                # Implementation here
                pass
    """

    def __init__(self, project_root: Optional[Path] = None) -> None:
        """
        Initialize the analyzer.

        Args:
            project_root: Root directory of the project to analyze.
                         If None, uses current working directory.
        """
        self.project_root = project_root or Path.cwd()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._start_time: Optional[float] = None

    @abstractmethod
    def analyze(self, **kwargs: Any) -> AnalysisResult[T]:
        """
        Perform the analysis.

        Must be implemented by subclasses.

        Args:
            **kwargs: Analysis-specific parameters

        Returns:
            AnalysisResult containing findings and metadata
        """
        pass

    def _start_timing(self) -> None:
        """Start timing the analysis."""
        self._start_time = time.perf_counter()

    def _stop_timing(self) -> float:
        """
        Stop timing and return elapsed time in milliseconds.

        Returns:
            Elapsed time in milliseconds
        """
        if self._start_time is None:
            return 0.0
        elapsed = (time.perf_counter() - self._start_time) * 1000
        self._start_time = None
        return elapsed

    def _read_file_safe(self, path: Path, encoding: str = 'utf-8') -> Optional[str]:
        """
        Safely read a file, returning None on error.

        Args:
            path: Path to the file
            encoding: File encoding (default: utf-8)

        Returns:
            File contents or None if reading failed
        """
        try:
            return path.read_text(encoding=encoding)
        except (OSError, UnicodeDecodeError) as e:
            self.logger.warning(f"Could not read {path}: {e}")
            return None

    def _find_files(self, pattern: str, recursive: bool = True) -> List[Path]:
        """
        Find files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.kt")
            recursive: Whether to search recursively

        Returns:
            List of matching file paths
        """
        if recursive and not pattern.startswith('**'):
            pattern = f"**/{pattern}"
        return list(self.project_root.glob(pattern))

    def _create_result(
            self,
            findings: List[T],
            metadata: Optional[Dict[str, Any]] = None,
            errors: Optional[List[str]] = None
    ) -> AnalysisResult[T]:
        """
        Create an analysis result with timing information.

        Args:
            findings: List of findings
            metadata: Optional metadata dictionary
            errors: Optional list of errors

        Returns:
            AnalysisResult with timing and success status
        """
        duration = self._stop_timing()
        return AnalysisResult(
            findings=findings,
            metadata=metadata or {},
            duration_ms=duration,
            success=not errors,
            errors=errors or []
        )
