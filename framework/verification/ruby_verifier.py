"""RubyVerifier — extracted from verifier.py (mechanical split; see base.py)."""

from pathlib import Path
from typing import List

from framework.verification.base import (
    LanguageVerifier,
    VerificationCategory,
    VerificationIssue,
    VerificationLevel,
    VerificationResult,
)


class RubyVerifier(LanguageVerifier):
    """Ruby test file verifier"""

    @property
    def language(self) -> str:
        """The language this verifier handles."""
        return "ruby"

    @property
    def file_extensions(self) -> List[str]:
        """File extensions this verifier claims (dispatch by suffix)."""
        return [".rb"]

    def verify(self, file_path: Path) -> VerificationResult:
        """Verify Ruby test file"""
        issues: List[VerificationIssue] = []

        try:
            content = file_path.read_text()

            # Check if it's a test file
            is_test_file = "_spec.rb" in file_path.name or "_test.rb" in file_path.name

            if is_test_file:
                # Check for RSpec
                if "_spec.rb" in file_path.name:
                    if "RSpec" not in content and "describe" not in content:
                        issues.append(
                            VerificationIssue(
                                level=VerificationLevel.WARNING,
                                category=VerificationCategory.IMPORTS,
                                message="RSpec spec file missing RSpec or describe block",
                                file_path=str(file_path),
                            )
                        )

                # Check for Minitest
                if "_test.rb" in file_path.name:
                    if "Minitest" not in content and "class" not in content:
                        issues.append(
                            VerificationIssue(
                                level=VerificationLevel.WARNING,
                                category=VerificationCategory.IMPORTS,
                                message="Minitest file missing test class",
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
