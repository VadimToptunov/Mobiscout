"""Verification models and the language-verifier base class.

Extracted from verifier.py during the module decomposition. Imported by every
language verifier and by the MultiLanguageVerifier orchestrator; behaviour is
unchanged.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class VerificationLevel(Enum):
    """Verification severity levels"""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


class VerificationCategory(Enum):
    """Verification categories"""

    SYNTAX = "syntax"
    IMPORTS = "imports"
    STRUCTURE = "structure"
    SELECTORS = "selectors"
    BEST_PRACTICES = "best_practices"
    COMPATIBILITY = "compatibility"


@dataclass
class VerificationIssue:
    """A single verification issue"""

    level: VerificationLevel
    category: VerificationCategory
    message: str
    file_path: str
    line_number: int = 0
    column: int = 0
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this issue to a plain dict (enum values flattened)."""
        return {
            "level": self.level.value,
            "category": self.category.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "suggestion": self.suggestion,
        }


@dataclass
class VerificationResult:
    """Results of verification"""

    language: str
    file_path: str
    success: bool
    issues: List[VerificationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        """Number of ERROR-level issues in this result."""
        return len([i for i in self.issues if i.level == VerificationLevel.ERROR])

    @property
    def warning_count(self) -> int:
        """Number of WARNING-level issues in this result."""
        return len([i for i in self.issues if i.level == VerificationLevel.WARNING])

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this result (with derived error/warning counts) to a dict."""
        return {
            "language": self.language,
            "file_path": self.file_path,
            "success": self.success,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [i.to_dict() for i in self.issues],
            "metadata": self.metadata,
        }


class LanguageVerifier(ABC):
    """Abstract base class for language-specific verifiers.

    ``verify()`` is a template method: it reads the file, guards the read with a
    uniform ``(OSError, UnicodeDecodeError)`` handler, computes ``success`` from
    the collected issues, and assembles the :class:`VerificationResult`.
    Subclasses supply only the language-specific inspection via
    :meth:`_run_checks` (and, optionally, :meth:`_collect_metadata`).
    """

    @property
    @abstractmethod
    def language(self) -> str:
        """Language name"""

    @property
    @abstractmethod
    def file_extensions(self) -> List[str]:
        """Supported file extensions"""

    def verify(self, file_path: Path) -> VerificationResult:
        """Read ``file_path`` and verify it via the language-specific checks.

        Handles file IO and result assembly once for every language; subclasses
        only implement :meth:`_run_checks`.
        """
        issues: List[VerificationIssue] = []

        try:
            content = file_path.read_text(encoding="utf-8")

            issues = self._run_checks(content, file_path)

            success = not any(i.level == VerificationLevel.ERROR for i in issues)

            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=success,
                issues=issues,
                metadata=self._collect_metadata(content, issues),
            )

        except (OSError, UnicodeDecodeError) as e:
            issues.append(
                VerificationIssue(
                    level=VerificationLevel.ERROR,
                    category=VerificationCategory.SYNTAX,
                    message=f"Failed to read file: {e}",
                    file_path=str(file_path),
                )
            )
            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=False,
                issues=issues,
            )

    @abstractmethod
    def _run_checks(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Run the language-specific checks over already-read ``content``.

        Called by :meth:`verify` with the file's text; must return the list of
        issues found (empty list when clean). File IO and result assembly are
        handled by the base class.
        """

    def _collect_metadata(self, content: str, issues: List[VerificationIssue]) -> Dict[str, Any]:
        """Metadata to attach to the result. Defaults to none; override as needed."""
        return {}

    def supports_file(self, file_path: Path) -> bool:
        """Check if this verifier supports the file"""
        return file_path.suffix in self.file_extensions
