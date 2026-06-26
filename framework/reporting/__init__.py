"""
Test reporting and result aggregation

Unified test reporter supporting multiple formats:
- HTML reports
- Markdown reports
- PDF reports
- Allure reports
- JUnit XML
- Test execution analytics
"""

from .allure_generator import AllureGenerator
from .base_reporter import BaseReporter, ReportFormat as BaseReportFormat, ReportMetadata
from .junit_parser import JUnitParser
from .report_generator import (
    ReportGenerator,
    HTMLReportGenerator,
    MarkdownReportGenerator,
    JSONReportGenerator,
    TestSuiteResult,
    TestResult,
    TestStatus,
)
from .unified_reporter import UnifiedReporter, ReportFormat

__all__ = [
    "UnifiedReporter",
    "ReportFormat",
    "JUnitParser",
    "AllureGenerator",
    "ReportGenerator",
    "HTMLReportGenerator",
    "MarkdownReportGenerator",
    "JSONReportGenerator",
    "TestSuiteResult",
    "TestResult",
    "TestStatus",
    "BaseReporter",
    "BaseReportFormat",
    "ReportMetadata",
]
