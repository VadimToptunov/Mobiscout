"""JavaScriptVerifier — extracted from verifier.py (mechanical split; see base.py)."""

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


class JavaScriptVerifier(LanguageVerifier):
    """JavaScript/TypeScript test file verifier"""

    @property
    def language(self) -> str:
        """The language this verifier handles."""
        return "javascript"

    @property
    def file_extensions(self) -> List[str]:
        """File extensions this verifier claims (dispatch by suffix)."""
        return [".js", ".ts", ".jsx", ".tsx"]

    def verify(self, file_path: Path) -> VerificationResult:
        """Verify JavaScript/TypeScript test file"""
        issues: List[VerificationIssue] = []

        try:
            content = file_path.read_text()

            # Check test framework
            is_test_file = ".test." in file_path.name or ".spec." in file_path.name

            if is_test_file:
                frameworks = ["jest", "mocha", "jasmine", "vitest"]
                if not any(f in content.lower() for f in ["describe(", "it(", "test("]):
                    issues.append(
                        VerificationIssue(
                            level=VerificationLevel.WARNING,
                            category=VerificationCategory.STRUCTURE,
                            message="Test file has no test cases",
                            file_path=str(file_path),
                        )
                    )

            # Check for async/await without proper handling
            for i, line in enumerate(content.splitlines(), 1):
                if "async " in line and "await" not in content[content.find(line) :]:
                    if "test(" in line or "it(" in line:
                        issues.append(
                            VerificationIssue(
                                level=VerificationLevel.INFO,
                                category=VerificationCategory.BEST_PRACTICES,
                                message="Async test without await",
                                file_path=str(file_path),
                                line_number=i,
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
