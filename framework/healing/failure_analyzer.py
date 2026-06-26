"""
Failure analyzer

Analyzes test failures to detect broken selectors.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any


class FailureType(Enum):
    """Type of test failure"""
    SELECTOR_NOT_FOUND = "selector_not_found"
    TIMEOUT = "timeout"
    ASSERTION_ERROR = "assertion_error"
    OTHER = "other"


@dataclass
class SelectorFailure:
    """Represents a selector failure"""
    test_name: str
    test_file: Path
    selector_type: str  # id, xpath, css, accessibility_id
    selector_value: str
    failure_type: FailureType
    error_message: str
    page_object_file: Optional[Path] = None
    page_object_class: Optional[str] = None
    element_name: Optional[str] = None
    screenshot_path: Optional[Path] = None
    page_source_path: Optional[Path] = None

    @property
    def selector_tuple(self) -> tuple:
        """Return selector as tuple (type, value)"""
        return (self.selector_type, self.selector_value)

    @property
    def selector(self) -> str:
        """Return selector as string"""
        return f"{self.selector_type}={self.selector_value}"

    @property
    def element_info(self) -> Dict[str, Any]:
        """Return element info dictionary"""
        return {
            "selector_type": self.selector_type,
            "selector_value": self.selector_value,
            "element_name": self.element_name,
            "page_object_class": self.page_object_class
        }

    @property
    def page_source(self) -> Optional[str]:
        """Return page source content if available"""
        if self.page_source_path and self.page_source_path.exists():
            return self.page_source_path.read_text()
        return None


class FailureAnalyzer:
    """
    Analyzes test failures to identify broken selectors
    """

    # Common error patterns for selector failures
    SELECTOR_ERROR_PATTERNS = [
        r"NoSuchElementException.*element.*not found",
        r"TimeoutException.*element.*not found",
        r"Unable to find element",
        r"Element.*not found",
        r"Could not find element",
        r"No element found",
        r"Selector.*did not match any elements",
    ]

    def __init__(self):
        self.failures: List[SelectorFailure] = []

    def analyze_junit_results(self, junit_path: Path) -> List[SelectorFailure]:
        """
        Analyze JUnit XML test results

        Args:
            junit_path: Path to JUnit XML file

        Returns:
            List of detected selector failures
        """
        self.failures = []

        try:
            tree = ET.parse(junit_path)
            root = tree.getroot()

            # Handle both <testsuite> and <testsuites> root
            if root.tag == 'testsuites':
                suites = root.findall('testsuite')
            else:
                suites = [root]

            for suite in suites:
                self._analyze_suite(suite)

        except (OSError, ET.ParseError) as e:
            print(f"Error parsing JUnit XML: {e}")

        return self.failures

    def analyze_test_results(self, results_path: Path, screenshot_dir: Optional[Path] = None) -> List[SelectorFailure]:
        """
        Analyze test results (auto-detect format)

        Args:
            results_path: Path to test results file (JUnit XML, pytest output, etc.)
            screenshot_dir: Optional path to screenshots directory

        Returns:
            List of detected selector failures
        """
        if not results_path.exists():
            return []

        # Detect format based on extension or content
        if results_path.suffix == '.xml':
            return self.analyze_junit_results(results_path)
        else:
            # Assume text output
            content = results_path.read_text()
            return self.analyze_pytest_output(content)

    def _analyze_suite(self, suite: ET.Element):
        """Analyze single test suite"""
        for testcase in suite.findall('testcase'):
            self._analyze_testcase(testcase)

    def _analyze_testcase(self, testcase: ET.Element):
        """Analyze single test case"""
        test_name = testcase.get('name', 'Unknown')
        classname = testcase.get('classname', '')
        test_file = Path(classname.replace('.', '/') + '.py')

        # Check for failures or errors
        failure = testcase.find('failure')
        error = testcase.find('error')

        failure_elem = failure if failure is not None else error
        if failure_elem is None:
            return  # Test passed

        error_message = failure_elem.get('message', '')
        error_text = failure_elem.text or ''
        full_error = f"{error_message}\n{error_text}"

        # Check if it's a selector failure
        if self._is_selector_failure(full_error):
            selector_info = self._extract_selector_info(full_error)
            if selector_info:
                failure = SelectorFailure(
                    test_name=test_name,
                    test_file=test_file,
                    selector_type=selector_info['type'],
                    selector_value=selector_info['value'],
                    failure_type=FailureType.SELECTOR_NOT_FOUND,
                    error_message=error_message,
                )
                self.failures.append(failure)

    def _is_selector_failure(self, error_text: str) -> bool:
        """Check if error is related to selector failure"""
        for pattern in self.SELECTOR_ERROR_PATTERNS:
            if re.search(pattern, error_text, re.IGNORECASE):
                return True
        return False

    def _extract_selector_info(self, error_text: str) -> Optional[Dict[str, str]]:
        """
        Extract selector information from error message

        Returns:
            Dict with 'type' and 'value' or None
        """
        # Try to extract selector from common patterns
        patterns = [
            # Appium/Selenium patterns
            r"Using='(\w+)',.*?value='([^']+)'",
            r"By\.(\w+):\s*([^\s\)]+)",
            r"selector.*?\((\w+),\s*['\"]([^'\"]+)['\"]",
            # XPath patterns
            r"xpath['\"]?\s*[=:]\s*['\"]([^'\"]+)['\"]",
            # ID patterns
            r"id['\"]?\s*[=:]\s*['\"]([^'\"]+)['\"]",
            # CSS patterns
            r"css['\"]?\s*[=:]\s*['\"]([^'\"]+)['\"]",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    return {
                        'type': groups[0].lower(),
                        'value': groups[1]
                    }
                elif len(groups) == 1:
                    # Assume xpath if only value captured
                    return {
                        'type': 'xpath',
                        'value': groups[0]
                    }

        return None

    def analyze_pytest_output(self, output: str) -> List[SelectorFailure]:
        """
        Analyze pytest output text

        Args:
            output: Pytest output text

        Returns:
            List of detected selector failures
        """
        self.failures = []

        # Parse pytest output for failures
        # This is a simplified version - real implementation would be more robust
        lines = output.split('\n')

        current_test = None
        error_buffer = []

        for line in lines:
            # Detect test start
            if '::test_' in line or 'FAILED' in line:
                if current_test and error_buffer:
                    # Process previous test
                    error_text = '\n'.join(error_buffer)
                    if self._is_selector_failure(error_text):
                        selector_info = self._extract_selector_info(error_text)
                        if selector_info:
                            failure = SelectorFailure(
                                test_name=current_test,
                                test_file=Path("unknown.py"),
                                selector_type=selector_info['type'],
                                selector_value=selector_info['value'],
                                failure_type=FailureType.SELECTOR_NOT_FOUND,
                                error_message=error_text[:200],
                            )
                            self.failures.append(failure)

                current_test = line.split('::')[-1] if '::' in line else None
                error_buffer = []
            else:
                error_buffer.append(line)

        return self.failures

    def enrich_with_screenshots(self, screenshots_dir: Path):
        """
        Link failures with screenshots

        Args:
            screenshots_dir: Directory containing failure screenshots
        """
        for failure in self.failures:
            # Look for screenshot matching test name
            pattern = f"*{failure.test_name}*.png"
            matches = list(screenshots_dir.glob(pattern))
            if matches:
                failure.screenshot_path = matches[0]

    def enrich_with_page_source(self, page_source_dir: Path):
        """
        Link failures with page source dumps

        Args:
            page_source_dir: Directory containing page source files
        """
        for failure in self.failures:
            # Look for page source matching test name
            pattern = f"*{failure.test_name}*.xml"
            matches = list(page_source_dir.glob(pattern))
            if matches:
                failure.page_source_path = matches[0]

    def enrich_with_page_objects(self, page_objects_dir: Path):
        """
        Find Page Object files containing the failing selectors

        Args:
            page_objects_dir: Directory containing Page Object files
        """
        for failure in self.failures:
            # Search for selector in Page Object files
            for po_file in page_objects_dir.rglob('*.py'):
                try:
                    content = po_file.read_text()
                    # Look for selector definition
                    if failure.selector_value in content:
                        failure.page_object_file = po_file
                        # Try to extract class name
                        class_match = re.search(r'class\s+(\w+)', content)
                        if class_match:
                            failure.page_object_class = class_match.group(1)
                        break
                except (OSError, UnicodeDecodeError):
                    continue

    def generate_report(self) -> str:
        """Generate human-readable report of failures"""
        if not self.failures:
            return "No selector failures detected."

        report = "SELECTOR FAILURE ANALYSIS\n"
        report += "=" * 80 + "\n\n"
        report += f"Found {len(self.failures)} selector failure(s):\n\n"

        for i, failure in enumerate(self.failures, 1):
            report += f"{i}. Test: {failure.test_name}\n"
            report += f"   Selector: ({failure.selector_type}, '{failure.selector_value}')\n"
            report += f"   File: {failure.test_file}\n"

            if failure.page_object_file:
                report += f"   Page Object: {failure.page_object_file}\n"
                if failure.page_object_class:
                    report += f"   Class: {failure.page_object_class}\n"

            if failure.screenshot_path:
                report += f"   Screenshot: {failure.screenshot_path}\n"

            if failure.page_source_path:
                report += f"   Page Source: {failure.page_source_path}\n"

            report += f"   Error: {failure.error_message[:100]}...\n"
            report += "\n"

        report += "=" * 80 + "\n"

        return report
