"""
Test selector based on code changes

Selects tests to run based on file changes and dependencies.
"""

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Set, Dict

from .change_analyzer import FileChange, ChangeType


class ImpactLevel(Enum):
    """Level of impact on tests"""

    HIGH = "high"  # Direct dependency
    MEDIUM = "medium"  # Indirect dependency
    LOW = "low"  # Related directory
    NONE = "none"  # No impact


@dataclass(eq=False)
class TestImpact:
    """Represents test impact from changes"""

    test_file: Path
    test_name: str
    impact_level: ImpactLevel
    reasons: List[str]  # Why this test is impacted

    # A test is identified by its file and name alone. The generated __eq__ also
    # compared impact_level and reasons, so the same test found by two selection
    # strategies compared unequal while hashing equal, and a set kept both — which
    # double-counted it in the report and in the runtime estimate.
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TestImpact):
            return NotImplemented
        return (self.test_file, self.test_name) == (other.test_file, other.test_name)

    def __hash__(self) -> int:
        return hash((self.test_file, self.test_name))


# Strongest impact first, for merging two findings about the same test.
_IMPACT_RANK = {
    ImpactLevel.HIGH: 0,
    ImpactLevel.MEDIUM: 1,
    ImpactLevel.LOW: 2,
    ImpactLevel.NONE: 3,
}


class TestSelector:
    """
    Selects tests based on code changes
    """

    def __init__(self, project_root: Path, test_root: Path) -> None:
        """
        Initialize test selector

        Args:
            project_root: Root directory of the project
            test_root: Root directory of tests
        """
        self.project_root = project_root
        self.test_root = test_root
        self._test_cache: Dict[Path, List[str]] = {}
        self._dependency_cache: Dict[Path, Set[Path]] = {}

    def select_tests(self, changes: List[FileChange], selection_strategy: str = "smart") -> List[TestImpact]:
        """
        Select tests to run based on changes

        Args:
            changes: List of file changes
            selection_strategy: Selection strategy
                - "smart": Intelligent selection based on dependencies
                - "changed_files": Only tests for changed files
                - "all": All tests

        Returns:
            List of tests to run with impact information
        """
        if selection_strategy == "all":
            return self._select_all_tests()

        impacted_tests: Dict[tuple, TestImpact] = {}

        for change in changes:
            if change.change_type == ChangeType.DELETED:
                continue

            # Direct test file changes
            if self._is_test_file(change.path):
                tests = self._get_tests_from_file(change.path)
                for test_name in tests:
                    self._merge_impact(
                        impacted_tests,
                        TestImpact(
                            test_file=change.path,
                            test_name=test_name,
                            impact_level=ImpactLevel.HIGH,
                            reasons=["Test file directly modified"],
                        ),
                    )

            # Source file changes - find dependent tests
            elif selection_strategy == "smart":
                for dependent in self._find_dependent_tests(change.path):
                    self._merge_impact(impacted_tests, dependent)

        # Sort by impact level
        return sorted(impacted_tests.values(), key=lambda t: (t.impact_level.value, str(t.test_file), t.test_name))

    @staticmethod
    def _merge_impact(impacted: Dict[tuple, TestImpact], impact: TestImpact) -> None:
        """Record an impact, folding it into an existing entry for the same test.

        Several strategies routinely find the same test (a test both named after
        the changed module and importing it); keeping one entry per strategy
        inflated the selected-test count and the runtime estimate built from it.
        """
        key = (impact.test_file, impact.test_name)
        existing = impacted.get(key)

        if existing is None:
            impacted[key] = impact
            return

        for reason in impact.reasons:
            if reason not in existing.reasons:
                existing.reasons.append(reason)

        if _IMPACT_RANK[impact.impact_level] < _IMPACT_RANK[existing.impact_level]:
            existing.impact_level = impact.impact_level

    def _is_test_file(self, path: Path) -> bool:
        """Check if file is a test file"""
        try:
            # relative =  # Unusedpath.relative_to(self.test_root)
            name = path.name
            return name.startswith("test_") or name.endswith("_test.py") or "test" in path.parts
        except ValueError:
            return False

    def _get_tests_from_file(self, test_file: Path) -> List[str]:
        """Extract test names from test file"""
        if test_file in self._test_cache:
            return self._test_cache[test_file]

        tests = []

        try:
            content = test_file.read_text(encoding="utf-8")
            tree = ast.parse(content)

            for node in tree.body:
                # Module-level test functions
                if isinstance(node, ast.FunctionDef):
                    if node.name.startswith("test_"):
                        tests.append(node.name)

                # Test classes
                elif isinstance(node, ast.ClassDef):
                    if node.name.startswith("Test"):
                        for item in node.body:
                            if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                                tests.append(f"{node.name}.{item.name}")
        except (OSError, SyntaxError, UnicodeDecodeError):
            pass

        self._test_cache[test_file] = tests
        return tests

    def _find_dependent_tests(self, source_file: Path) -> List[TestImpact]:
        """Find tests that depend on a source file"""
        impacted: Dict[tuple, TestImpact] = {}

        # Strategy 1: Find tests in same directory
        directory_tests = self._find_tests_in_directory(source_file.parent)
        for test_file, test_name in directory_tests:
            self._merge_impact(
                impacted,
                TestImpact(
                    test_file=test_file,
                    test_name=test_name,
                    impact_level=ImpactLevel.MEDIUM,
                    reasons=[f"Located in same directory as {source_file.name}"],
                ),
            )

        # Strategy 2: Find tests with similar names
        similar_tests = self._find_tests_by_naming_convention(source_file)
        for test_file, test_name in similar_tests:
            self._merge_impact(
                impacted,
                TestImpact(
                    test_file=test_file,
                    test_name=test_name,
                    impact_level=ImpactLevel.HIGH,
                    reasons=[f"Naming convention matches {source_file.name}"],
                ),
            )

        # Strategy 3: Find tests that import this file
        importing_tests = self._find_tests_importing_file(source_file)
        for test_file, test_name in importing_tests:
            self._merge_impact(
                impacted,
                TestImpact(
                    test_file=test_file,
                    test_name=test_name,
                    impact_level=ImpactLevel.HIGH,
                    reasons=[f"Imports {source_file.name}"],
                ),
            )

        return list(impacted.values())

    def _find_tests_in_directory(self, directory: Path) -> List[tuple]:
        """Find all tests in a directory"""
        tests = []

        # Look for test files in same directory
        for test_file in directory.glob("test_*.py"):
            if test_file.is_file():
                test_names = self._get_tests_from_file(test_file)
                tests.extend([(test_file, name) for name in test_names])

        for test_file in directory.glob("*_test.py"):
            if test_file.is_file():
                test_names = self._get_tests_from_file(test_file)
                tests.extend([(test_file, name) for name in test_names])

        return tests

    def _find_tests_by_naming_convention(self, source_file: Path) -> List[tuple]:
        """Find tests that match naming convention"""
        tests = []

        # Look for test_<filename>.py or <filename>_test.py
        stem = source_file.stem

        test_patterns = [f"test_{stem}.py", f"{stem}_test.py", f"test_{stem}_*.py"]

        for pattern in test_patterns:
            for test_file in self.test_root.rglob(pattern):
                if test_file.is_file():
                    test_names = self._get_tests_from_file(test_file)
                    tests.extend([(test_file, name) for name in test_names])

        return tests

    def _find_tests_importing_file(self, source_file: Path) -> List[tuple]:
        """Find tests that import the source file"""
        tests = []

        try:
            # Get relative import path
            relative_path = source_file.relative_to(self.project_root)
            module_name = str(relative_path.with_suffix("")).replace("/", ".")

            # Search all test files
            for test_file in self.test_root.rglob("test_*.py"):
                if not test_file.is_file():
                    continue

                try:
                    content = test_file.read_text(encoding="utf-8")
                    tree = ast.parse(content)

                    # Check imports
                    imports_source = False
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if module_name in alias.name:
                                    imports_source = True
                                    break
                        elif isinstance(node, ast.ImportFrom):
                            if node.module and module_name in node.module:
                                imports_source = True
                                break

                    if imports_source:
                        test_names = self._get_tests_from_file(test_file)
                        tests.extend([(test_file, name) for name in test_names])

                except (OSError, SyntaxError, UnicodeDecodeError):
                    continue

        except (ValueError, OSError):
            pass

        return tests

    def _select_all_tests(self) -> List[TestImpact]:
        """Select all available tests"""
        all_tests = []

        for test_file in self.test_root.rglob("test_*.py"):
            if test_file.is_file():
                test_names = self._get_tests_from_file(test_file)
                for name in test_names:
                    all_tests.append(
                        TestImpact(
                            test_file=test_file,
                            test_name=name,
                            impact_level=ImpactLevel.NONE,
                            reasons=["Running all tests"],
                        )
                    )

        return all_tests

    def estimate_runtime(self, tests: List[TestImpact]) -> float:
        """
        Estimate total runtime for selected tests

        Args:
            tests: List of tests to run

        Returns:
            Estimated runtime in seconds
        """
        # Rough estimate: 1 second per test on average
        # In reality, would load from historical data
        return len(tests) * 1.0

    def generate_report(self, tests: List[TestImpact]) -> str:
        """Generate selection report"""
        if not tests:
            return "No tests selected"

        report = f"Selected {len(tests)} tests:\n\n"

        # Group by impact level
        by_impact: Dict[str, List[TestImpact]] = {}
        for test in tests:
            level = test.impact_level.value
            if level not in by_impact:
                by_impact[level] = []
            by_impact[level].append(test)

        for level in ["high", "medium", "low"]:
            if level in by_impact:
                report += f"\n{level.upper()} Impact ({len(by_impact[level])} tests):\n"
                for test in by_impact[level][:10]:  # Show first 10
                    report += f"  - {test.test_file.name}::{test.test_name}\n"
                    report += f"    Reason: {', '.join(test.reasons)}\n"

                if len(by_impact[level]) > 10:
                    report += f"  ... and {len(by_impact[level]) - 10} more\n"

        report += f"\nEstimated runtime: {self.estimate_runtime(tests):.1f}s\n"

        return report
