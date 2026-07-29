"""Canonical test-result value objects, shared across subsystems.

Before this module, ``TestResult`` was redefined four times and
``TestSuiteResult`` three times, with overlapping-but-divergent fields, and the
copies compared unequal across subsystems. This centralises the
``TestStatus``-based reporting shape (formerly duplicated in
``reporting.report_generator``) so reporting and the dashboard share one type by
identity.

Scope note (deliberately *not* forced in here):

* ``reporting.unified_reporter.TestResult`` / ``TestSuite`` keep a **string**
  status because they are the raw JUnit-parse intermediate produced by
  ``JUnitParser`` (the parser emits ``"passed"``/``"failed"`` strings straight
  from XML). Folding them in would change the producer/consumer status contract,
  so they stay separate; ``cli.dashboard_commands`` already adapts them to the
  canonical dashboard ``TestResult``.
* ``execution.test_runner.TestResult`` / ``TestSuiteResult`` use a different,
  test-locked vocabulary (``duration_ms``, ``message``, ``stacktrace``,
  ``suite_name``, ``total_tests`` …). Renaming those to the canonical names would
  break their behaviour contract, so they stay separate too. Their ``status`` is
  already the canonical :class:`~framework.domain.status.TestStatus`.

The dashboard's persistence-oriented result (which additionally requires
``id``/``timestamp``/``file_path``) is a thin subclass of :class:`TestResult`
rather than extra optional fields polluting this shared type.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from framework.domain.status import TestStatus


@dataclass
class TestResult:
    """A single test's outcome (canonical, ``TestStatus``-typed).

    Superset of the reporting fields; every field bar ``name`` has a sensible
    default so no consumer loses a field it used to set.
    """

    name: str
    status: TestStatus = TestStatus.PASSED
    duration: float = 0.0
    error_message: Optional[str] = None
    screenshot_path: Optional[Path] = None
    stack_trace: Optional[str] = None
    test_file: Optional[str] = None
    test_class: Optional[str] = None


@dataclass
class TestSuiteResult:
    """Aggregate outcome of running a suite of :class:`TestResult`."""

    name: str
    tests: List[TestResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    environment: Dict[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Total duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def total_count(self) -> int:
        return len(self.tests)

    @property
    def passed_count(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.PASSED)

    @property
    def failed_count(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.FAILED)

    @property
    def skipped_count(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.SKIPPED)

    @property
    def error_count(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.ERROR)

    @property
    def pass_rate(self) -> float:
        """Pass rate as percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.passed_count / self.total_count) * 100
