"""
Test Runner - Executes test suites and collects results

This module provides the TestRunner class for executing tests
across different platforms and collecting results.
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class TestResultStatus(Enum):
    """Test result status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Result of a single test execution."""
    name: str
    status: TestResultStatus
    duration_ms: float
    message: Optional[str] = None
    stacktrace: Optional[str] = None
    screenshot_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestSuiteResult:
    """Result of running a test suite."""
    suite_name: str
    start_time: datetime
    end_time: datetime
    tests: List[TestResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tests(self) -> int:
        return len(self.tests)

    @property
    def passed_tests(self) -> int:
        return sum(1 for t in self.tests if t.status == TestResultStatus.PASSED)

    @property
    def failed_tests(self) -> int:
        return sum(1 for t in self.tests if t.status == TestResultStatus.FAILED)

    @property
    def skipped_tests(self) -> int:
        return sum(1 for t in self.tests if t.status == TestResultStatus.SKIPPED)

    @property
    def error_tests(self) -> int:
        return sum(1 for t in self.tests if t.status == TestResultStatus.ERROR)

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'suite_name': self.suite_name,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'duration_seconds': self.duration_seconds,
            'total_tests': self.total_tests,
            'passed_tests': self.passed_tests,
            'failed_tests': self.failed_tests,
            'skipped_tests': self.skipped_tests,
            'error_tests': self.error_tests,
            'tests': [
                {
                    'name': t.name,
                    'status': t.status.value,
                    'duration_ms': t.duration_ms,
                    'message': t.message,
                }
                for t in self.tests
            ],
            'metadata': self.metadata,
        }


class TestRunner:
    """
    Test Runner for executing test suites.

    Supports multiple test frameworks:
    - pytest (Python)
    - JUnit (Java/Kotlin)
    - XCTest (iOS)
    """

    def __init__(
            self,
            working_dir: Optional[Path] = None,
            timeout_seconds: int = 300,
    ):
        self.working_dir = working_dir or Path.cwd()
        self.timeout_seconds = timeout_seconds

    def run_tests(
            self,
            test_path: Path,
            framework: str = "pytest",
            extra_args: Optional[List[str]] = None,
    ) -> TestSuiteResult:
        """
        Run tests and return results.

        Args:
            test_path: Path to test file or directory
            framework: Test framework (pytest, junit, xctest)
            extra_args: Additional command line arguments

        Returns:
            TestSuiteResult with test outcomes
        """
        start_time = datetime.now()

        if framework == "pytest":
            results = self._run_pytest(test_path, extra_args)
        elif framework == "junit":
            results = self._run_junit(test_path, extra_args)
        else:
            results = []

        end_time = datetime.now()

        return TestSuiteResult(
            suite_name=str(test_path.name),
            start_time=start_time,
            end_time=end_time,
            tests=results,
        )

    def _run_pytest(
            self,
            test_path: Path,
            extra_args: Optional[List[str]] = None,
    ) -> List[TestResult]:
        """Run pytest and collect results."""
        args = ["python", "-m", "pytest", str(test_path), "--json-report", "-v"]
        if extra_args:
            args.extend(extra_args)

        try:
            subprocess.run(
                args,
                cwd=self.working_dir,
                timeout=self.timeout_seconds,
                capture_output=True,
            )
        except subprocess.TimeoutExpired:
            return [TestResult(
                name="timeout",
                status=TestResultStatus.ERROR,
                duration_ms=self.timeout_seconds * 1000,
                message="Test execution timed out",
            )]
        except (subprocess.SubprocessError, OSError) as e:
            return [TestResult(
                name="error",
                status=TestResultStatus.ERROR,
                duration_ms=0,
                message=str(e),
            )]

        # Parse results from json report if available
        report_path = self.working_dir / ".report.json"
        if report_path.exists():
            return self._parse_pytest_report(report_path)

        return []

    def _run_junit(
            self,
            test_path: Path,
            extra_args: Optional[List[str]] = None,
    ) -> List[TestResult]:
        """Run JUnit tests (placeholder)."""
        # Would use gradle/maven to run tests
        return []

    def _parse_pytest_report(self, report_path: Path) -> List[TestResult]:
        """Parse pytest JSON report."""
        try:
            with open(report_path) as f:
                data = json.load(f)

            results = []
            for test in data.get("tests", []):
                status_map = {
                    "passed": TestResultStatus.PASSED,
                    "failed": TestResultStatus.FAILED,
                    "skipped": TestResultStatus.SKIPPED,
                    "error": TestResultStatus.ERROR,
                }
                results.append(TestResult(
                    name=test.get("nodeid", "unknown"),
                    status=status_map.get(test.get("outcome", "error"), TestResultStatus.ERROR),
                    duration_ms=test.get("duration", 0) * 1000,
                    message=test.get("call", {}).get("longrepr"),
                ))
            return results
        except (json.JSONDecodeError, IOError):
            return []

    def run_test(
            self,
            test_name: str,
            test_path: Optional[Path] = None,
            framework: str = "pytest",
    ) -> TestResult:
        """
        Run a single test and return result.

        Args:
            test_name: Name of the test to run
            test_path: Optional path to test file
            framework: Test framework

        Returns:
            TestResult for the single test
        """
        path = test_path or Path(test_name)
        start_time = datetime.now()

        try:
            if framework == "pytest":
                args = ["python", "-m", "pytest", str(path), "-v", "-k", test_name]
                result = subprocess.run(
                    args,
                    cwd=self.working_dir,
                    timeout=self.timeout_seconds,
                    capture_output=True,
                    text=True,
                )
                end_time = datetime.now()
                duration_ms = (end_time - start_time).total_seconds() * 1000

                if result.returncode == 0:
                    return TestResult(
                        name=test_name,
                        status=TestResultStatus.PASSED,
                        duration_ms=duration_ms,
                    )
                else:
                    return TestResult(
                        name=test_name,
                        status=TestResultStatus.FAILED,
                        duration_ms=duration_ms,
                        message=result.stdout[:500] if result.stdout else None,
                        stacktrace=result.stderr[:1000] if result.stderr else None,
                    )
        except subprocess.TimeoutExpired:
            return TestResult(
                name=test_name,
                status=TestResultStatus.ERROR,
                duration_ms=self.timeout_seconds * 1000,
                message="Test execution timed out",
            )
        except (subprocess.SubprocessError, OSError) as e:
            return TestResult(
                name=test_name,
                status=TestResultStatus.ERROR,
                duration_ms=0,
                message=str(e),
            )
