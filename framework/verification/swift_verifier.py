"""SwiftVerifier — extracted from verifier.py (mechanical split; see base.py)."""

import re
from pathlib import Path
from typing import List

from framework.verification.base import (
    LanguageVerifier,
    VerificationCategory,
    VerificationIssue,
    VerificationLevel,
)


class SwiftVerifier(LanguageVerifier):
    """Swift test file verifier"""

    @property
    def language(self) -> str:
        """The language this verifier handles."""
        return "swift"

    @property
    def file_extensions(self) -> List[str]:
        """File extensions this verifier claims (dispatch by suffix)."""
        return [".swift"]

    def _run_checks(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Verify Swift test file"""
        issues: List[VerificationIssue] = []

        # Check imports
        if "XCTest" in file_path.name or "Test" in file_path.name:
            if "import XCTest" not in content:
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.IMPORTS,
                        message="Test file missing XCTest import",
                        file_path=str(file_path),
                    )
                )

        # Check for XCTestCase subclass
        if "Test" in file_path.name:
            if "XCTestCase" not in content:
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message="Test class should inherit from XCTestCase",
                        file_path=str(file_path),
                    )
                )

        # Check for test methods
        test_pattern = r"func\s+test\w+\s*\("
        if "Test" in file_path.name:
            if not re.search(test_pattern, content):
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message="No test methods found (should start with 'test')",
                        file_path=str(file_path),
                    )
                )

        return issues
