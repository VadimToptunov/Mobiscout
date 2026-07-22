"""PythonVerifier — extracted from verifier.py (mechanical split; see base.py)."""

import ast
import re
from pathlib import Path
from typing import List, Set

from framework.verification.base import (
    LanguageVerifier,
    VerificationCategory,
    VerificationIssue,
    VerificationLevel,
    VerificationResult,
)


class PythonVerifier(LanguageVerifier):
    """Python test file verifier"""

    @property
    def language(self) -> str:
        """The language this verifier handles."""
        return "python"

    @property
    def file_extensions(self) -> List[str]:
        """File extensions this verifier claims (dispatch by suffix)."""
        return [".py"]

    def verify(self, file_path: Path) -> VerificationResult:
        """Verify Python test file"""
        issues: List[VerificationIssue] = []

        try:
            content = file_path.read_text()

            # Syntax check
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.ERROR,
                        category=VerificationCategory.SYNTAX,
                        message=f"Syntax error: {e.msg}",
                        file_path=str(file_path),
                        line_number=e.lineno or 0,
                        column=e.offset or 0,
                    )
                )
                return VerificationResult(
                    language=self.language,
                    file_path=str(file_path),
                    success=False,
                    issues=issues,
                )

            # Check imports
            issues.extend(self._check_imports(tree, file_path))

            # Check test structure
            issues.extend(self._check_test_structure(tree, file_path))

            # Check selectors
            issues.extend(self._check_selectors(content, file_path))

            # Check best practices
            issues.extend(self._check_best_practices(tree, content, file_path))

            success = not any(i.level == VerificationLevel.ERROR for i in issues)

            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=success,
                issues=issues,
                metadata={"line_count": len(content.splitlines())},
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

    def _check_imports(self, tree: ast.AST, file_path: Path) -> List[VerificationIssue]:
        """Check import statements"""
        issues = []
        found_imports: Set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found_imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    found_imports.add(node.module.split(".")[0])

        # Check if it's a test file
        if file_path.name.startswith("test_"):
            if "pytest" not in found_imports and "unittest" not in found_imports:
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.IMPORTS,
                        message="Test file missing test framework import (pytest or unittest)",
                        file_path=str(file_path),
                        suggestion="Add 'import pytest' at the top of the file",
                    )
                )

        return issues

    def _check_test_structure(self, tree: ast.AST, file_path: Path) -> List[VerificationIssue]:
        """Check test structure"""
        issues = []
        test_functions = []
        test_classes = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith("test_"):
                    test_functions.append(node)
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("Test"):
                    test_classes.append(node)

        # Check if test file has tests
        if file_path.name.startswith("test_"):
            if not test_functions and not test_classes:
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message="Test file has no test functions or classes",
                        file_path=str(file_path),
                        suggestion="Add test functions starting with 'test_' prefix",
                    )
                )

        # Check for empty test functions
        for func in test_functions:
            if len(func.body) == 1 and isinstance(func.body[0], ast.Pass):
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message=f"Empty test function: {func.name}",
                        file_path=str(file_path),
                        line_number=func.lineno,
                        suggestion="Implement the test or add pytest.skip() with reason",
                    )
                )

        return issues

    def _check_selectors(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Check selector definitions"""
        issues = []

        # Check for hardcoded XPath
        xpath_pattern = r'By\.xpath\(["\']//\w+'
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(xpath_pattern, line):
                # Check for fragile XPath patterns
                if "/div[" in line or "/span[" in line:
                    issues.append(
                        VerificationIssue(
                            level=VerificationLevel.WARNING,
                            category=VerificationCategory.SELECTORS,
                            message="Potentially fragile XPath using index-based selection",
                            file_path=str(file_path),
                            line_number=i,
                            suggestion="Use accessibility_id or resource-id instead",
                        )
                    )

        # Check for deprecated selectors
        deprecated_patterns = [
            (r"find_element_by_\w+", "find_element_by_* is deprecated, use find_element(By.*, ...)"),
            (r"find_elements_by_\w+", "find_elements_by_* is deprecated, use find_elements(By.*, ...)"),
        ]

        for i, line in enumerate(content.splitlines(), 1):
            for pattern, message in deprecated_patterns:
                if re.search(pattern, line):
                    issues.append(
                        VerificationIssue(
                            level=VerificationLevel.WARNING,
                            category=VerificationCategory.COMPATIBILITY,
                            message=message,
                            file_path=str(file_path),
                            line_number=i,
                        )
                    )

        return issues

    def _check_best_practices(self, tree: ast.AST, content: str, file_path: Path) -> List[VerificationIssue]:
        """Check best practices"""
        issues = []

        # Check for sleep calls
        for i, line in enumerate(content.splitlines(), 1):
            if "time.sleep(" in line or "sleep(" in line:
                issues.append(
                    VerificationIssue(
                        level=VerificationLevel.INFO,
                        category=VerificationCategory.BEST_PRACTICES,
                        message="Using time.sleep() - consider using explicit waits instead",
                        file_path=str(file_path),
                        line_number=i,
                        suggestion="Use WebDriverWait with expected_conditions",
                    )
                )

        # Check for missing docstrings
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if node.name.startswith("test_") or node.name.startswith("Test"):
                    if not ast.get_docstring(node):
                        issues.append(
                            VerificationIssue(
                                level=VerificationLevel.SUGGESTION,
                                category=VerificationCategory.BEST_PRACTICES,
                                message=f"Missing docstring for {node.name}",
                                file_path=str(file_path),
                                line_number=node.lineno,
                                suggestion="Add a docstring describing the test purpose",
                            )
                        )

        return issues
