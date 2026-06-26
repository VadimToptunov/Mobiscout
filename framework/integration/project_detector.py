"""
Project structure detection and analysis

Scans existing test automation projects to understand:
- Directory structure and organization
- Test framework used (pytest, unittest, etc.)
- Page Object patterns
- Fixtures and utilities
- Test coverage
"""

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Set


@dataclass
class ProjectStructure:
    """Detected project structure"""
    root_dir: Path
    test_framework: str  # pytest, unittest, robot, behave
    page_objects_dir: Optional[Path] = None
    tests_dir: Optional[Path] = None
    fixtures_dir: Optional[Path] = None
    utilities_dir: Optional[Path] = None
    data_dir: Optional[Path] = None
    reports_dir: Optional[Path] = None

    # Detected files
    page_object_files: List[Path] = field(default_factory=list)
    test_files: List[Path] = field(default_factory=list)
    fixture_files: List[Path] = field(default_factory=list)
    utility_files: List[Path] = field(default_factory=list)

    # Conventions
    page_object_suffix: str = "_page.py"
    test_prefix: str = "test_"
    base_page_class: Optional[str] = None

    # Coverage
    total_tests: int = 0
    total_page_objects: int = 0
    screens_covered: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "root_dir": str(self.root_dir),
            "test_framework": self.test_framework,
            "structure": {
                "page_objects_dir": str(self.page_objects_dir) if self.page_objects_dir else None,
                "tests_dir": str(self.tests_dir) if self.tests_dir else None,
                "fixtures_dir": str(self.fixtures_dir) if self.fixtures_dir else None,
                "utilities_dir": str(self.utilities_dir) if self.utilities_dir else None,
                "data_dir": str(self.data_dir) if self.data_dir else None,
            },
            "conventions": {
                "page_object_suffix": self.page_object_suffix,
                "test_prefix": self.test_prefix,
                "base_page_class": self.base_page_class,
            },
            "coverage": {
                "total_tests": self.total_tests,
                "total_page_objects": self.total_page_objects,
                "screens_covered": list(self.screens_covered),
            }
        }


class ProjectDetector:
    """
    Detects and analyzes existing test automation projects
    """

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        if not self.project_dir.exists():
            raise ValueError(f"Project directory does not exist: {project_dir}")

    def scan(self) -> ProjectStructure:
        """Scan project and build structure model"""
        print(f"Scanning project: {self.project_dir}")

        structure = ProjectStructure(
            root_dir=self.project_dir,
            test_framework=self._detect_test_framework()
        )

        # Find directories
        structure.page_objects_dir = self._find_directory([
            "page_objects", "pages", "page_object", "pom", "screens"
        ])
        structure.tests_dir = self._find_directory([
            "tests", "test", "test_cases", "testcases", "test_suites"
        ])
        structure.fixtures_dir = self._find_directory([
            "fixtures", "fixture", "test_fixtures"
        ])
        structure.utilities_dir = self._find_directory([
            "utilities", "utils", "helpers", "common"
        ])
        structure.data_dir = self._find_directory([
            "data", "test_data", "testdata", "resources"
        ])
        structure.reports_dir = self._find_directory([
            "reports", "report", "test_reports", "output", "results"
        ])

        # Find files
        if structure.page_objects_dir:
            structure.page_object_files = self._find_python_files(structure.page_objects_dir)
            structure.total_page_objects = len(structure.page_object_files)

        if structure.tests_dir:
            structure.test_files = self._find_test_files(structure.tests_dir)
            structure.total_tests = self._count_tests(structure.test_files)

        if structure.fixtures_dir:
            structure.fixture_files = self._find_python_files(structure.fixtures_dir)

        # Also search for conftest.py files
        conftest_files = list(self.project_dir.rglob("conftest.py"))
        structure.fixture_files.extend(conftest_files)

        if structure.utilities_dir:
            structure.utility_files = self._find_python_files(structure.utilities_dir)

        # Detect conventions
        structure.page_object_suffix = self._detect_page_object_suffix(structure.page_object_files)
        structure.test_prefix = self._detect_test_prefix(structure.test_files)
        structure.base_page_class = self._detect_base_page_class(structure.page_object_files)

        # Analyze coverage
        structure.screens_covered = self._extract_covered_screens(structure.page_object_files)

        print(f"✓ Detected {structure.test_framework} project")
        print(f"✓ Found {structure.total_page_objects} Page Objects")
        print(f"✓ Found {structure.total_tests} tests")
        print(f"✓ Coverage: {len(structure.screens_covered)} screens")

        return structure

    def _detect_test_framework(self) -> str:
        """Detect which test framework is used"""
        # Check for pytest
        if (self.project_dir / "pytest.ini").exists():
            return "pytest"
        if (self.project_dir / "pyproject.toml").exists():
            content = (self.project_dir / "pyproject.toml").read_text()
            if "[tool.pytest" in content:
                return "pytest"

        # Check conftest.py (pytest convention)
        if list(self.project_dir.rglob("conftest.py")):
            return "pytest"

        # Check for unittest
        test_files = list(self.project_dir.rglob("test_*.py"))
        if test_files:
            for test_file in test_files[:5]:  # Sample first 5
                content = test_file.read_text()
                if "import unittest" in content or "from unittest import" in content:
                    return "unittest"
                if "import pytest" in content or "@pytest" in content:
                    return "pytest"

        # Check for Robot Framework
        if list(self.project_dir.rglob("*.robot")):
            return "robot"

        # Check for behave
        if (self.project_dir / "features").exists():
            return "behave"

        # Default assumption
        return "pytest"

    def _find_directory(self, possible_names: List[str]) -> Optional[Path]:
        """Find directory by possible names"""
        for name in possible_names:
            # Check direct child
            candidate = self.project_dir / name
            if candidate.exists() and candidate.is_dir():
                return candidate

            # Check nested (up to 2 levels)
            matches = list(self.project_dir.glob(f"*/{name}"))
            if matches:
                return matches[0]

            matches = list(self.project_dir.glob(f"*/*/{name}"))
            if matches:
                return matches[0]

        return None

    def _find_python_files(self, directory: Path) -> List[Path]:
        """Find all Python files in directory"""
        if not directory or not directory.exists():
            return []
        return [f for f in directory.rglob("*.py") if not f.name.startswith("__")]

    def _find_test_files(self, directory: Path) -> List[Path]:
        """Find test files"""
        if not directory or not directory.exists():
            return []

        test_files = []
        # Standard pytest/unittest pattern
        test_files.extend(directory.rglob("test_*.py"))
        test_files.extend(directory.rglob("*_test.py"))

        return list(set(test_files))  # Remove duplicates

    def _count_tests(self, test_files: List[Path]) -> int:
        """Count total number of test functions/methods"""
        count = 0
        for test_file in test_files:
            try:
                content = test_file.read_text()
                tree = ast.parse(content)

                # Only iterate top-level nodes to avoid double-counting
                # Test methods in classes will be counted in the class iteration
                for node in tree.body:
                    # Test functions (module-level)
                    if isinstance(node, ast.FunctionDef):
                        if node.name.startswith("test_"):
                            count += 1

                    # Test methods in classes
                    elif isinstance(node, ast.ClassDef):
                        for item in node.body:
                            if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                                count += 1
            except (OSError, SyntaxError, UnicodeDecodeError) as e:
                print(f"Warning: Could not parse {test_file}: {e}")
                continue

        return count

    def _detect_page_object_suffix(self, page_object_files: List[Path]) -> str:
        """Detect Page Object file naming convention"""
        if not page_object_files:
            return "_page.py"

        # Analyze file names
        suffixes = {}
        for file in page_object_files:
            name = file.stem  # filename without extension
            if "_page" in name:
                suffixes["_page.py"] = suffixes.get("_page.py", 0) + 1
            elif "Page" in file.name:
                suffixes["Page.py"] = suffixes.get("Page.py", 0) + 1
            elif "_screen" in name:
                suffixes["_screen.py"] = suffixes.get("_screen.py", 0) + 1

        # Return most common
        if suffixes:
            return max(suffixes, key=suffixes.get)
        return "_page.py"

    def _detect_test_prefix(self, test_files: List[Path]) -> str:
        """Detect test file naming convention"""
        if not test_files:
            return "test_"

        # Count patterns
        prefix_count = sum(1 for f in test_files if f.name.startswith("test_"))
        suffix_count = sum(1 for f in test_files if f.name.endswith("_test.py"))

        return "test_" if prefix_count >= suffix_count else "_test"

    def _detect_base_page_class(self, page_object_files: List[Path]) -> Optional[str]:
        """Detect base Page Object class name"""
        base_candidates = ["BasePage", "BaseScreen", "PageObject", "Page"]

        for file in page_object_files:
            if "base" in file.stem.lower():
                try:
                    content = file.read_text()
                    tree = ast.parse(content)

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            if node.name in base_candidates:
                                return node.name
                except (OSError, SyntaxError, UnicodeDecodeError):
                    continue

        # Check if BasePage is imported in other files
        for file in page_object_files[:10]:  # Sample first 10
            try:
                content = file.read_text()
                for candidate in base_candidates:
                    if "from .base" in content and candidate in content:
                        return candidate
                    if "import base_page" in content and candidate in content:
                        return candidate
            except (OSError, UnicodeDecodeError):
                continue

        return None

    def _extract_covered_screens(self, page_object_files: List[Path]) -> Set[str]:
        """Extract list of screens/pages covered by Page Objects"""
        screens = set()

        for file in page_object_files:
            # Extract from filename
            name = file.stem
            # Remove suffixes
            for suffix in ["_page", "_screen", "Page", "Screen"]:
                if suffix in name:
                    name = name.replace(suffix, "")

            # Convert to title case
            screen_name = name.replace("_", " ").title().replace(" ", "")
            if screen_name and screen_name.lower() != "base":
                screens.add(screen_name)

        return screens

    def save_analysis(self, output_path: Path):
        """Save analysis to JSON file"""
        structure = self.scan()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(structure.to_dict(), f, indent=2)

        print(f"\n✓ Analysis saved to: {output_path}")
