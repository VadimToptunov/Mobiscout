"""KotlinVerifier — extracted from verifier.py (mechanical split; see base.py)."""

from pathlib import Path
from typing import List

from framework.verification.base import (
    LanguageVerifier,
    VerificationCategory,
    VerificationIssue,
    VerificationLevel,
)


class KotlinVerifier(LanguageVerifier):
    """Kotlin test file verifier"""

    @property
    def language(self) -> str:
        """The language this verifier handles."""
        return "kotlin"

    @property
    def file_extensions(self) -> List[str]:
        """File extensions this verifier claims (dispatch by suffix)."""
        return [".kt", ".kts"]

    def _run_checks(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Verify Kotlin test file"""
        issues: List[VerificationIssue] = []

        # Check imports
        issues.extend(self._check_imports(content, file_path))

        # Check test structure
        issues.extend(self._check_test_structure(content, file_path))

        # Check selectors
        issues.extend(self._check_selectors(content, file_path))

        return issues

    def _check_imports(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Check Kotlin imports"""
        issues = []

        if "Test" in file_path.name or "test" in file_path.name.lower():
            if "org.junit" not in content and "kotlin.test" not in content:
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.IMPORTS,
                        message="Test file missing JUnit or kotlin.test import",
                        file_path=str(file_path),
                    )
                )

        return issues

    def _check_test_structure(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Check Kotlin test structure"""
        issues = []

        # Check for @Test annotations
        if "Test" in file_path.name:
            if "@Test" not in content and "@ParameterizedTest" not in content:
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message="Test file has no @Test annotations",
                        file_path=str(file_path),
                    )
                )

        return issues

    def _check_selectors(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Check Kotlin selectors"""
        issues = []

        for i, line in enumerate(content.splitlines(), 1):
            # Check for deprecated patterns
            if "findElement(" in line and "By.xpath" in line:
                if "//div[" in line or "//span[" in line:
                    issues.append(
                        VerificationIssue(
                            level=VerificationLevel.WARNING,
                            category=VerificationCategory.SELECTORS,
                            message="Fragile XPath selector",
                            file_path=str(file_path),
                            line_number=i,
                            suggestion="Use By.id or MobileBy.AccessibilityId",
                        )
                    )

        return issues
