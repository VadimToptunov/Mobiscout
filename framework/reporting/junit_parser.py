"""
JUnit XML parser

Parses JUnit XML test results.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from .unified_reporter import TestResult, TestSuite


class JUnitParser:
    """
    Parser for JUnit XML format
    """

    def parse(self, junit_path: Path) -> TestSuite:
        """
        Parse JUnit XML file

        Args:
            junit_path: Path to JUnit XML file

        Returns:
            TestSuite with parsed results
        """
        tree = ET.parse(junit_path)
        root = tree.getroot()

        # Handle both <testsuite> and <testsuites> root elements
        if root.tag == 'testsuites':
            suites = root.findall('testsuite')
            if not suites:
                raise ValueError("No testsuites found in XML")
            # Use first suite for now (could aggregate multiple)
            suite_elem = suites[0]
        else:
            suite_elem = root

        suite_name = suite_elem.get('name', 'Unknown Suite')
        timestamp = suite_elem.get('timestamp', '')
        duration = float(suite_elem.get('time', 0))

        tests = []
        for testcase in suite_elem.findall('testcase'):
            test = self._parse_testcase(testcase)
            tests.append(test)

        return TestSuite(
            name=suite_name,
            tests=tests,
            timestamp=timestamp,
            duration=duration
        )

    def _parse_testcase(self, testcase: ET.Element) -> TestResult:
        """Parse individual test case"""
        name = testcase.get('name', 'Unknown Test')
        classname = testcase.get('classname', '')
        duration = float(testcase.get('time', 0))

        # Determine status and error info
        status = 'passed'
        error_message = None
        stack_trace = None

        failure = testcase.find('failure')
        error = testcase.find('error')
        skipped = testcase.find('skipped')

        if failure is not None:
            status = 'failed'
            error_message = failure.get('message', '')
            stack_trace = failure.text
        elif error is not None:
            status = 'failed'
            error_message = error.get('message', '')
            stack_trace = error.text
        elif skipped is not None:
            status = 'skipped'
            error_message = skipped.get('message', 'Test skipped')

        # Combine classname and name for full test name
        full_name = f"{classname}.{name}" if classname else name

        return TestResult(
            name=full_name,
            status=status,
            duration=duration,
            error_message=error_message,
            stack_trace=stack_trace
        )
