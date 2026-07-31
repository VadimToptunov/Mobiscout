"""
JUnit XML parser

Parses JUnit XML test results.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from .unified_reporter import TestResult, TestSuite


class JUnitParser:
    """
    Parser for JUnit XML format
    """

    def parse_all(self, junit_path: Path) -> List[TestSuite]:
        """Parse every ``<testsuite>`` in a JUnit XML file, one TestSuite each.

        A ``<testsuites>`` document commonly holds several suites (one per test
        file / framework); returning them separately keeps their grouping in the
        report. Use :meth:`parse` when a single aggregated suite is wanted.
        """
        root = ET.parse(junit_path).getroot()
        return self._suites_from_root(root)

    def parse(self, junit_path: Path) -> TestSuite:
        """Parse a JUnit XML file into a single suite.

        A ``<testsuites>`` document with multiple ``<testsuite>`` children is
        aggregated into one suite so **no test case is dropped** (the old code
        kept only the first suite). Use :meth:`parse_all` to keep suites apart.
        """
        suites = self.parse_all(junit_path)
        if len(suites) == 1:
            return suites[0]

        root = ET.parse(junit_path).getroot()
        name = root.get("name") or "Aggregated Results"
        tests = [t for s in suites for t in s.tests]
        timestamp = root.get("timestamp") or next((s.timestamp for s in suites if s.timestamp), "")
        # Prefer the document's own total time; else sum the suites'.
        root_time = root.get("time")
        duration = float(root_time) if root_time else sum(s.duration for s in suites)
        return TestSuite(name=name, tests=tests, timestamp=timestamp, duration=duration)

    def _suites_from_root(self, root: ET.Element) -> List[TestSuite]:
        """The suites under a JUnit root: each ``<testsuite>`` child of a
        ``<testsuites>`` wrapper, or the root itself when it is a bare
        ``<testsuite>`` (or a wrapper carrying test cases directly)."""
        if root.tag == "testsuites":
            suite_elems = root.findall("testsuite")
            if suite_elems:
                return [self._suite_from_elem(e) for e in suite_elems]
            # Non-standard: test cases sit directly under <testsuites>.
            return [self._suite_from_elem(root)]
        return [self._suite_from_elem(root)]

    def _suite_from_elem(self, suite_elem: ET.Element) -> TestSuite:
        """Build a TestSuite from one ``<testsuite>`` element. Test cases are
        collected at any depth so a suite that nests sub-suites keeps them all."""
        name = suite_elem.get("name", "Unknown Suite")
        timestamp = suite_elem.get("timestamp", "")
        duration = float(suite_elem.get("time", 0))
        tests = [self._parse_testcase(tc) for tc in suite_elem.iter("testcase")]
        return TestSuite(name=name, tests=tests, timestamp=timestamp, duration=duration)

    def _parse_testcase(self, testcase: ET.Element) -> TestResult:
        """Parse individual test case"""
        name = testcase.get("name", "Unknown Test")
        classname = testcase.get("classname", "")
        duration = float(testcase.get("time", 0))

        # Determine status and error info
        status = "passed"
        error_message = None
        stack_trace = None

        failure = testcase.find("failure")
        error = testcase.find("error")
        skipped = testcase.find("skipped")

        if failure is not None:
            status = "failed"
            error_message = failure.get("message", "")
            stack_trace = failure.text
        elif error is not None:
            status = "failed"
            error_message = error.get("message", "")
            stack_trace = error.text
        elif skipped is not None:
            status = "skipped"
            error_message = skipped.get("message", "Test skipped")

        # Combine classname and name for full test name
        full_name = f"{classname}.{name}" if classname else name

        return TestResult(
            name=full_name, status=status, duration=duration, error_message=error_message, stack_trace=stack_trace
        )
