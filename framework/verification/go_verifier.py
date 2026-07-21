"""GoVerifier — extracted from verifier.py (mechanical split; see base.py)."""

import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from framework.verification.base import (
    LanguageVerifier,
    VerificationCategory,
    VerificationIssue,
    VerificationLevel,
    VerificationResult,
)


class GoVerifier(LanguageVerifier):
    """Go test file verifier"""

    @property
    def language(self) -> str:
        """The language this verifier handles."""
        return "go"

    @property
    def file_extensions(self) -> List[str]:
        """File extensions this verifier claims (dispatch by suffix)."""
        return [".go"]

    def verify(self, file_path: Path) -> VerificationResult:
        """Verify Go test file"""
        issues: List[VerificationIssue] = []

        try:
            content = file_path.read_text()

            # Check if it's a test file
            is_test_file = file_path.name.endswith("_test.go")

            if is_test_file:
                # Check for testing import
                if '"testing"' not in content:
                    issues.append(
                        VerificationIssue(
                            level=VerificationLevel.WARNING,
                            category=VerificationCategory.IMPORTS,
                            message="Test file missing testing package import",
                            file_path=str(file_path),
                        )
                    )

                # Check for test functions
                if "func Test" not in content:
                    issues.append(
                        VerificationIssue(
                            level=VerificationLevel.WARNING,
                            category=VerificationCategory.STRUCTURE,
                            message="No test functions found",
                            file_path=str(file_path),
                        )
                    )

                # Check for *testing.T parameter
                test_func_pattern = r"func\s+Test\w+\s*\(\s*\w+\s+\*testing\.T\s*\)"
                if "func Test" in content and not re.search(test_func_pattern, content):
                    issues.append(
                        VerificationIssue(
                            level=VerificationLevel.ERROR,
                            category=VerificationCategory.STRUCTURE,
                            message="Test function missing *testing.T parameter",
                            file_path=str(file_path),
                        )
                    )

            success = not any(i.level == VerificationLevel.ERROR for i in issues)

            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=success,
                issues=issues,
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
