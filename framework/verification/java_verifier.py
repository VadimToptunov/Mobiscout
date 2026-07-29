"""JavaVerifier — heuristic checks for generated Java test sources.

Codegen emits ``.java`` via the ``java_testng`` and ``java_cucumber`` targets,
but the verification package had no Java verifier. This fills that gap with the
same lightweight, text-based inspection style as the other JVM/native verifiers
(no external toolchain required). File IO and result assembly are provided by
:class:`~framework.verification.base.LanguageVerifier`.
"""

from pathlib import Path
from typing import List

from framework.verification.base import (
    LanguageVerifier,
    VerificationCategory,
    VerificationIssue,
    VerificationLevel,
)


class JavaVerifier(LanguageVerifier):
    """Java test file verifier (TestNG / JUnit / Cucumber step definitions)."""

    @property
    def language(self) -> str:
        """The language this verifier handles."""
        return "java"

    @property
    def file_extensions(self) -> List[str]:
        """File extensions this verifier claims (dispatch by suffix)."""
        return [".java"]

    def _run_checks(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Verify Java test file"""
        issues: List[VerificationIssue] = []

        name = file_path.name
        is_test_file = "Test" in name or "Steps" in name or "IT" in name

        if is_test_file:
            # Check for a test framework import (TestNG, JUnit, or Cucumber).
            if not any(pkg in content for pkg in ("org.testng", "org.junit", "io.cucumber")):
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.IMPORTS,
                        message="Test file missing test framework import (TestNG, JUnit, or Cucumber)",
                        file_path=str(file_path),
                    )
                )

            # Check for test annotations (@Test or Cucumber step annotations).
            if not any(anno in content for anno in ("@Test", "@Given", "@When", "@Then")):
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message="Test file has no test annotations (@Test / @Given / @When / @Then)",
                        file_path=str(file_path),
                    )
                )

        # Structural sanity: braces must balance. Mismatched braces mean the
        # source cannot compile, so surface it as an error.
        open_braces = content.count("{")
        close_braces = content.count("}")
        if open_braces != close_braces:
            issues.append(
                VerificationIssue(
                    level=VerificationLevel.ERROR,
                    category=VerificationCategory.SYNTAX,
                    message=f"Unbalanced braces: {open_braces} '{{' vs {close_braces} '}}'",
                    file_path=str(file_path),
                )
            )

        return issues
