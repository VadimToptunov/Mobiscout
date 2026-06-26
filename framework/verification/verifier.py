"""
Multi-Language Verification Module

STEP 12: Verifies test code across multiple programming languages.

Features:
- Syntax validation
- Import/dependency checking
- Test structure validation
- Selector pattern verification
- Cross-language consistency checks
"""

import ast
import json
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set


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
        return len([i for i in self.issues if i.level == VerificationLevel.ERROR])

    @property
    def warning_count(self) -> int:
        return len([i for i in self.issues if i.level == VerificationLevel.WARNING])

    def to_dict(self) -> Dict[str, Any]:
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
    """Abstract base class for language-specific verifiers"""

    @property
    @abstractmethod
    def language(self) -> str:
        """Language name"""
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> List[str]:
        """Supported file extensions"""
        pass

    @abstractmethod
    def verify(self, file_path: Path) -> VerificationResult:
        """Verify a file"""
        pass

    def supports_file(self, file_path: Path) -> bool:
        """Check if this verifier supports the file"""
        return file_path.suffix in self.file_extensions


class PythonVerifier(LanguageVerifier):
    """Python test file verifier"""

    @property
    def language(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> List[str]:
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
                issues.append(VerificationIssue(
                    level=VerificationLevel.ERROR,
                    category=VerificationCategory.SYNTAX,
                    message=f"Syntax error: {e.msg}",
                    file_path=str(file_path),
                    line_number=e.lineno or 0,
                    column=e.offset or 0,
                ))
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
            issues.append(VerificationIssue(
                level=VerificationLevel.ERROR,
                category=VerificationCategory.SYNTAX,
                message=f"Failed to read file: {e}",
                file_path=str(file_path),
            ))
            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=False,
                issues=issues,
            )

    def _check_imports(self, tree: ast.AST, file_path: Path) -> List[VerificationIssue]:
        """Check import statements"""
        issues = []
        required_imports = {"pytest", "appium", "selenium"}
        found_imports: Set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found_imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    found_imports.add(node.module.split('.')[0])

        # Check if it's a test file
        if file_path.name.startswith("test_"):
            if "pytest" not in found_imports and "unittest" not in found_imports:
                issues.append(VerificationIssue(
                    level=VerificationLevel.WARNING,
                    category=VerificationCategory.IMPORTS,
                    message="Test file missing test framework import (pytest or unittest)",
                    file_path=str(file_path),
                    suggestion="Add 'import pytest' at the top of the file",
                ))

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
                issues.append(VerificationIssue(
                    level=VerificationLevel.WARNING,
                    category=VerificationCategory.STRUCTURE,
                    message="Test file has no test functions or classes",
                    file_path=str(file_path),
                    suggestion="Add test functions starting with 'test_' prefix",
                ))

        # Check for empty test functions
        for func in test_functions:
            if len(func.body) == 1 and isinstance(func.body[0], ast.Pass):
                issues.append(VerificationIssue(
                    level=VerificationLevel.WARNING,
                    category=VerificationCategory.STRUCTURE,
                    message=f"Empty test function: {func.name}",
                    file_path=str(file_path),
                    line_number=func.lineno,
                    suggestion="Implement the test or add pytest.skip() with reason",
                ))

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
                    issues.append(VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.SELECTORS,
                        message="Potentially fragile XPath using index-based selection",
                        file_path=str(file_path),
                        line_number=i,
                        suggestion="Use accessibility_id or resource-id instead",
                    ))

        # Check for deprecated selectors
        deprecated_patterns = [
            (r'find_element_by_\w+', "find_element_by_* is deprecated, use find_element(By.*, ...)"),
            (r'find_elements_by_\w+', "find_elements_by_* is deprecated, use find_elements(By.*, ...)"),
        ]

        for i, line in enumerate(content.splitlines(), 1):
            for pattern, message in deprecated_patterns:
                if re.search(pattern, line):
                    issues.append(VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.COMPATIBILITY,
                        message=message,
                        file_path=str(file_path),
                        line_number=i,
                    ))

        return issues

    def _check_best_practices(self, tree: ast.AST, content: str, file_path: Path) -> List[VerificationIssue]:
        """Check best practices"""
        issues = []

        # Check for sleep calls
        for i, line in enumerate(content.splitlines(), 1):
            if "time.sleep(" in line or "sleep(" in line:
                issues.append(VerificationIssue(
                    level=VerificationLevel.INFO,
                    category=VerificationCategory.BEST_PRACTICES,
                    message="Using time.sleep() - consider using explicit waits instead",
                    file_path=str(file_path),
                    line_number=i,
                    suggestion="Use WebDriverWait with expected_conditions",
                ))

        # Check for missing docstrings
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if node.name.startswith("test_") or node.name.startswith("Test"):
                    if not ast.get_docstring(node):
                        issues.append(VerificationIssue(
                            level=VerificationLevel.SUGGESTION,
                            category=VerificationCategory.BEST_PRACTICES,
                            message=f"Missing docstring for {node.name}",
                            file_path=str(file_path),
                            line_number=node.lineno,
                            suggestion="Add a docstring describing the test purpose",
                        ))

        return issues


class KotlinVerifier(LanguageVerifier):
    """Kotlin test file verifier"""

    @property
    def language(self) -> str:
        return "kotlin"

    @property
    def file_extensions(self) -> List[str]:
        return [".kt", ".kts"]

    def verify(self, file_path: Path) -> VerificationResult:
        """Verify Kotlin test file"""
        issues: List[VerificationIssue] = []

        try:
            content = file_path.read_text()

            # Check imports
            issues.extend(self._check_imports(content, file_path))

            # Check test structure
            issues.extend(self._check_test_structure(content, file_path))

            # Check selectors
            issues.extend(self._check_selectors(content, file_path))

            success = not any(i.level == VerificationLevel.ERROR for i in issues)

            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=success,
                issues=issues,
            )

        except (OSError, UnicodeDecodeError) as e:
            issues.append(VerificationIssue(
                level=VerificationLevel.ERROR,
                category=VerificationCategory.SYNTAX,
                message=f"Failed to read file: {e}",
                file_path=str(file_path),
            ))
            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=False,
                issues=issues,
            )

    def _check_imports(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Check Kotlin imports"""
        issues = []

        if "Test" in file_path.name or "test" in file_path.name.lower():
            if "org.junit" not in content and "kotlin.test" not in content:
                issues.append(VerificationIssue(
                    level=VerificationLevel.WARNING,
                    category=VerificationCategory.IMPORTS,
                    message="Test file missing JUnit or kotlin.test import",
                    file_path=str(file_path),
                ))

        return issues

    def _check_test_structure(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Check Kotlin test structure"""
        issues = []

        # Check for @Test annotations
        if "Test" in file_path.name:
            if "@Test" not in content and "@ParameterizedTest" not in content:
                issues.append(VerificationIssue(
                    level=VerificationLevel.WARNING,
                    category=VerificationCategory.STRUCTURE,
                    message="Test file has no @Test annotations",
                    file_path=str(file_path),
                ))

        return issues

    def _check_selectors(self, content: str, file_path: Path) -> List[VerificationIssue]:
        """Check Kotlin selectors"""
        issues = []

        for i, line in enumerate(content.splitlines(), 1):
            # Check for deprecated patterns
            if "findElement(" in line and "By.xpath" in line:
                if "//div[" in line or "//span[" in line:
                    issues.append(VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.SELECTORS,
                        message="Fragile XPath selector",
                        file_path=str(file_path),
                        line_number=i,
                        suggestion="Use By.id or MobileBy.AccessibilityId",
                    ))

        return issues


class SwiftVerifier(LanguageVerifier):
    """Swift test file verifier"""

    @property
    def language(self) -> str:
        return "swift"

    @property
    def file_extensions(self) -> List[str]:
        return [".swift"]

    def verify(self, file_path: Path) -> VerificationResult:
        """Verify Swift test file"""
        issues: List[VerificationIssue] = []

        try:
            content = file_path.read_text()

            # Check imports
            if "XCTest" in file_path.name or "Test" in file_path.name:
                if "import XCTest" not in content:
                    issues.append(VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.IMPORTS,
                        message="Test file missing XCTest import",
                        file_path=str(file_path),
                    ))

            # Check for XCTestCase subclass
            if "Test" in file_path.name:
                if "XCTestCase" not in content:
                    issues.append(VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message="Test class should inherit from XCTestCase",
                        file_path=str(file_path),
                    ))

            # Check for test methods
            test_pattern = r'func\s+test\w+\s*\('
            if "Test" in file_path.name:
                if not re.search(test_pattern, content):
                    issues.append(VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message="No test methods found (should start with 'test')",
                        file_path=str(file_path),
                    ))

            success = not any(i.level == VerificationLevel.ERROR for i in issues)

            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=success,
                issues=issues,
            )

        except (OSError, UnicodeDecodeError) as e:
            issues.append(VerificationIssue(
                level=VerificationLevel.ERROR,
                category=VerificationCategory.SYNTAX,
                message=f"Failed to read file: {e}",
                file_path=str(file_path),
            ))
            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=False,
                issues=issues,
            )


class JavaScriptVerifier(LanguageVerifier):
    """JavaScript/TypeScript test file verifier"""

    @property
    def language(self) -> str:
        return "javascript"

    @property
    def file_extensions(self) -> List[str]:
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
                    issues.append(VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message="Test file has no test cases",
                        file_path=str(file_path),
                    ))

            # Check for async/await without proper handling
            for i, line in enumerate(content.splitlines(), 1):
                if "async " in line and "await" not in content[content.find(line):]:
                    if "test(" in line or "it(" in line:
                        issues.append(VerificationIssue(
                            level=VerificationLevel.INFO,
                            category=VerificationCategory.BEST_PRACTICES,
                            message="Async test without await",
                            file_path=str(file_path),
                            line_number=i,
                        ))

            success = not any(i.level == VerificationLevel.ERROR for i in issues)

            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=success,
                issues=issues,
            )

        except (OSError, UnicodeDecodeError) as e:
            issues.append(VerificationIssue(
                level=VerificationLevel.ERROR,
                category=VerificationCategory.SYNTAX,
                message=f"Failed to read file: {e}",
                file_path=str(file_path),
            ))
            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=False,
                issues=issues,
            )


class GoVerifier(LanguageVerifier):
    """Go test file verifier"""

    @property
    def language(self) -> str:
        return "go"

    @property
    def file_extensions(self) -> List[str]:
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
                    issues.append(VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.IMPORTS,
                        message="Test file missing testing package import",
                        file_path=str(file_path),
                    ))

                # Check for test functions
                if "func Test" not in content:
                    issues.append(VerificationIssue(
                        level=VerificationLevel.WARNING,
                        category=VerificationCategory.STRUCTURE,
                        message="No test functions found",
                        file_path=str(file_path),
                    ))

                # Check for *testing.T parameter
                test_func_pattern = r'func\s+Test\w+\s*\(\s*\w+\s+\*testing\.T\s*\)'
                if "func Test" in content and not re.search(test_func_pattern, content):
                    issues.append(VerificationIssue(
                        level=VerificationLevel.ERROR,
                        category=VerificationCategory.STRUCTURE,
                        message="Test function missing *testing.T parameter",
                        file_path=str(file_path),
                    ))

            success = not any(i.level == VerificationLevel.ERROR for i in issues)

            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=success,
                issues=issues,
            )

        except (OSError, UnicodeDecodeError) as e:
            issues.append(VerificationIssue(
                level=VerificationLevel.ERROR,
                category=VerificationCategory.SYNTAX,
                message=f"Failed to read file: {e}",
                file_path=str(file_path),
            ))
            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=False,
                issues=issues,
            )


class RubyVerifier(LanguageVerifier):
    """Ruby test file verifier"""

    @property
    def language(self) -> str:
        return "ruby"

    @property
    def file_extensions(self) -> List[str]:
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
                        issues.append(VerificationIssue(
                            level=VerificationLevel.WARNING,
                            category=VerificationCategory.IMPORTS,
                            message="RSpec spec file missing RSpec or describe block",
                            file_path=str(file_path),
                        ))

                # Check for Minitest
                if "_test.rb" in file_path.name:
                    if "Minitest" not in content and "class" not in content:
                        issues.append(VerificationIssue(
                            level=VerificationLevel.WARNING,
                            category=VerificationCategory.IMPORTS,
                            message="Minitest file missing test class",
                            file_path=str(file_path),
                        ))

            success = not any(i.level == VerificationLevel.ERROR for i in issues)

            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=success,
                issues=issues,
            )

        except (OSError, UnicodeDecodeError) as e:
            issues.append(VerificationIssue(
                level=VerificationLevel.ERROR,
                category=VerificationCategory.SYNTAX,
                message=f"Failed to read file: {e}",
                file_path=str(file_path),
            ))
            return VerificationResult(
                language=self.language,
                file_path=str(file_path),
                success=False,
                issues=issues,
            )


class MultiLanguageVerifier:
    """
    Multi-Language Verification Engine

    Verifies test code across all supported programming languages.
    """

    def __init__(self):
        self.verifiers: List[LanguageVerifier] = [
            PythonVerifier(),
            KotlinVerifier(),
            SwiftVerifier(),
            JavaScriptVerifier(),
            GoVerifier(),
            RubyVerifier(),
        ]

    def verify_file(self, file_path: Path) -> Optional[VerificationResult]:
        """Verify a single file"""
        for verifier in self.verifiers:
            if verifier.supports_file(file_path):
                return verifier.verify(file_path)
        return None

    def verify_directory(
        self,
        directory: Path,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None
    ) -> List[VerificationResult]:
        """Verify all files in a directory"""
        results = []
        exclude = exclude_patterns or ["node_modules", "venv", ".git", "__pycache__"]

        def should_exclude(path: Path) -> bool:
            return any(ex in str(path) for ex in exclude)

        if recursive:
            files = directory.rglob("*")
        else:
            files = directory.glob("*")

        for file_path in files:
            if file_path.is_file() and not should_exclude(file_path):
                result = self.verify_file(file_path)
                if result:
                    results.append(result)

        return results

    def get_summary(self, results: List[VerificationResult]) -> Dict[str, Any]:
        """Get verification summary"""
        total_files = len(results)
        passed = len([r for r in results if r.success])
        failed = total_files - passed
        total_errors = sum(r.error_count for r in results)
        total_warnings = sum(r.warning_count for r in results)

        by_language = {}
        for result in results:
            if result.language not in by_language:
                by_language[result.language] = {"files": 0, "passed": 0, "errors": 0, "warnings": 0}
            by_language[result.language]["files"] += 1
            if result.success:
                by_language[result.language]["passed"] += 1
            by_language[result.language]["errors"] += result.error_count
            by_language[result.language]["warnings"] += result.warning_count

        return {
            "total_files": total_files,
            "passed": passed,
            "failed": failed,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "pass_rate": (passed / total_files * 100) if total_files > 0 else 0,
            "by_language": by_language,
        }

    def export_report(self, results: List[VerificationResult], output_path: Path) -> None:
        """Export verification report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "summary": self.get_summary(results),
            "results": [r.to_dict() for r in results],
        }

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
