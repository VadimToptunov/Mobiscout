"""Test execution status — the single canonical definition.

Supersedes the copies formerly scattered across ``reporting.report_generator``,
``dashboard.models``, ``execution.parallel_executor`` and
``execution.test_runner`` (as ``TestResultStatus``), which could not be compared
across subsystems and made ``dashboard import-results`` dead-on-arrival.
"""

from enum import Enum


class TestStatus(str, Enum):
    """The outcome of a single test.

    ``str``-based so ``status == "passed"`` holds and ``.value`` yields the wire
    string used in reports and the dashboard DB.
    """

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
