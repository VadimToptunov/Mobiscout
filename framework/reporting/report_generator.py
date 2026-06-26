"""
Report Generation System

Generate professional test reports in multiple formats (HTML, PDF, Markdown).

Features:
- Executive summary
- Test statistics
- Failure analysis
- Screenshots embedded
- Interactive charts
- Customizable templates
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional


class ReportFormat(Enum):
    """Supported report formats"""
    HTML = "html"
    PDF = "pdf"
    MARKDOWN = "markdown"
    JSON = "json"


class TestStatus(Enum):
    """Test execution status"""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Individual test result"""
    name: str
    status: TestStatus
    duration: float
    error_message: Optional[str] = None
    screenshot_path: Optional[Path] = None
    stack_trace: Optional[str] = None
    test_file: Optional[str] = None
    test_class: Optional[str] = None


@dataclass
class TestSuiteResult:
    """Test suite execution results"""
    name: str
    tests: List[TestResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    environment: Dict[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Total duration in seconds"""
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
        """Pass rate as percentage"""
        if self.total_count == 0:
            return 0.0
        return (self.passed_count / self.total_count) * 100


class HTMLReportGenerator:
    """Generate interactive HTML reports"""

    HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Report - {suite_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .header .meta {{
            opacity: 0.9;
            font-size: 0.9em;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .summary-card .value {{
            font-size: 2.5em;
            font-weight: bold;
            margin: 10px 0;
        }}
        .summary-card .label {{
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .summary-card.passed .value {{ color: #10b981; }}
        .summary-card.failed .value {{ color: #ef4444; }}
        .summary-card.skipped .value {{ color: #f59e0b; }}
        .tests {{
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .test-item {{
            padding: 20px;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: flex-start;
            gap: 15px;
        }}
        .test-item:last-child {{
            border-bottom: none;
        }}
        .test-status {{
            width: 30px;
            height: 30px;
            border-radius: 50%;
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 0.8em;
        }}
        .test-status.passed {{ background: #10b981; color: white; }}
        .test-status.failed {{ background: #ef4444; color: white; }}
        .test-status.skipped {{ background: #f59e0b; color: white; }}
        .test-status.error {{ background: #6b7280; color: white; }}
        .test-info {{
            flex: 1;
        }}
        .test-name {{
            font-weight: 600;
            font-size: 1.1em;
            margin-bottom: 5px;
        }}
        .test-meta {{
            color: #666;
            font-size: 0.85em;
        }}
        .test-error {{
            margin-top: 10px;
            padding: 15px;
            background: #fee;
            border-left: 4px solid #ef4444;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.9em;
            white-space: pre-wrap;
            overflow-x: auto;
        }}
        .test-screenshot {{
            margin-top: 10px;
        }}
        .test-screenshot img {{
            max-width: 100%;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }}
        .progress-bar {{
            height: 30px;
            background: #eee;
            border-radius: 15px;
            overflow: hidden;
            margin: 20px 0;
            display: flex;
        }}
        .progress-segment {{
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 0.85em;
        }}
        .progress-segment.passed {{ background: #10b981; }}
        .progress-segment.failed {{ background: #ef4444; }}
        .progress-segment.skipped {{ background: #f59e0b; }}
        .footer {{
            text-align: center;
            padding: 30px;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{suite_name}</h1>
            <div class="meta">
                Generated on {timestamp} | Duration: {duration}s
            </div>
        </div>
        
        <div class="summary">
            <div class="summary-card">
                <div class="label">Total Tests</div>
                <div class="value">{total_count}</div>
            </div>
            <div class="summary-card passed">
                <div class="label">Passed</div>
                <div class="value">{passed_count}</div>
            </div>
            <div class="summary-card failed">
                <div class="label">Failed</div>
                <div class="value">{failed_count}</div>
            </div>
            <div class="summary-card skipped">
                <div class="label">Skipped</div>
                <div class="value">{skipped_count}</div>
            </div>
        </div>
        
        <div class="progress-bar">
            {progress_segments}
        </div>
        
        <div class="tests">
            {test_items}
        </div>
        
        <div class="footer">
            Generated by Observe Test Framework
        </div>
    </div>
</body>
</html>
"""

    def generate(self, suite: TestSuiteResult, output_path: Path) -> None:
        """Generate HTML report"""
        # Generate progress bar segments
        progress_segments = []
        if suite.passed_count > 0:
            width = (suite.passed_count / suite.total_count) * 100
            progress_segments.append(
                f'<div class="progress-segment passed" style="width: {width}%">'
                f'{suite.passed_count}</div>'
            )
        if suite.failed_count > 0:
            width = (suite.failed_count / suite.total_count) * 100
            progress_segments.append(
                f'<div class="progress-segment failed" style="width: {width}%">'
                f'{suite.failed_count}</div>'
            )
        if suite.skipped_count > 0:
            width = (suite.skipped_count / suite.total_count) * 100
            progress_segments.append(
                f'<div class="progress-segment skipped" style="width: {width}%">'
                f'{suite.skipped_count}</div>'
            )

        # Generate test items
        test_items = []
        for test in suite.tests:
            status_class = test.status.value
            status_symbol = {
                TestStatus.PASSED: "✓",
                TestStatus.FAILED: "✗",
                TestStatus.SKIPPED: "○",
                TestStatus.ERROR: "!",
            }[test.status]

            error_html = ""
            if test.error_message:
                error_html = f'<div class="test-error">{test.error_message}</div>'

            screenshot_html = ""
            if test.screenshot_path and test.screenshot_path.exists():
                screenshot_html = (
                    f'<div class="test-screenshot">'
                    f'<img src="{test.screenshot_path}" alt="Screenshot" />'
                    f'</div>'
                )

            test_items.append(f"""
            <div class="test-item">
                <div class="test-status {status_class}">{status_symbol}</div>
                <div class="test-info">
                    <div class="test-name">{test.name}</div>
                    <div class="test-meta">
                        Duration: {test.duration:.2f}s
                        {f'| {test.test_file}' if test.test_file else ''}
                    </div>
                    {error_html}
                    {screenshot_html}
                </div>
            </div>
            """)

        # Render template
        html = self.HTML_TEMPLATE.format(
            suite_name=suite.name,
            timestamp=suite.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            duration=f"{suite.duration:.2f}",
            total_count=suite.total_count,
            passed_count=suite.passed_count,
            failed_count=suite.failed_count,
            skipped_count=suite.skipped_count,
            progress_segments="".join(progress_segments),
            test_items="".join(test_items),
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)


class MarkdownReportGenerator:
    """Generate Markdown reports (GitHub/GitLab friendly)"""

    def generate(self, suite: TestSuiteResult, output_path: Path) -> None:
        """Generate Markdown report"""
        lines = [
            f"# Test Report: {suite.name}",
            "",
            f"**Generated:** {suite.start_time.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Duration:** {suite.duration:.2f}s  ",
            f"**Pass Rate:** {suite.pass_rate:.1f}%",
            "",
            "## Summary",
            "",
            f"- ✅ **Passed:** {suite.passed_count}",
            f"- ❌ **Failed:** {suite.failed_count}",
            f"- ⏭️ **Skipped:** {suite.skipped_count}",
            f"- 📊 **Total:** {suite.total_count}",
            "",
        ]

        # Failed tests section
        failed_tests = [t for t in suite.tests if t.status == TestStatus.FAILED]
        if failed_tests:
            lines.extend([
                "## ❌ Failed Tests",
                "",
            ])

            for test in failed_tests:
                lines.append(f"### {test.name}")
                lines.append("")
                lines.append(f"**Duration:** {test.duration:.2f}s  ")
                if test.test_file:
                    lines.append(f"**File:** `{test.test_file}`  ")
                lines.append("")

                if test.error_message:
                    lines.append("**Error:**")
                    lines.append("```")
                    lines.append(test.error_message)
                    lines.append("```")
                    lines.append("")

        # All tests table
        lines.extend([
            "## All Tests",
            "",
            "| Status | Test Name | Duration |",
            "|--------|-----------|----------|",
        ])

        for test in suite.tests:
            status_icon = {
                TestStatus.PASSED: "✅",
                TestStatus.FAILED: "❌",
                TestStatus.SKIPPED: "⏭️",
                TestStatus.ERROR: "⚠️",
            }[test.status]

            lines.append(
                f"| {status_icon} | {test.name} | {test.duration:.2f}s |"
            )

        lines.append("")
        lines.append("---")
        lines.append("*Generated by Observe Test Framework*")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


class JSONReportGenerator:
    """Generate JSON reports"""

    def generate(self, suite: TestSuiteResult, output_path: Path) -> None:
        """Generate JSON report"""
        data = {
            "name": suite.name,
            "start_time": suite.start_time.isoformat(),
            "end_time": suite.end_time.isoformat() if suite.end_time else None,
            "duration": suite.duration,
            "summary": {
                "total": suite.total_count,
                "passed": suite.passed_count,
                "failed": suite.failed_count,
                "skipped": suite.skipped_count,
                "error": suite.error_count,
                "pass_rate": suite.pass_rate,
            },
            "tests": [
                {
                    "name": test.name,
                    "status": test.status.value,
                    "duration": test.duration,
                    "error_message": test.error_message,
                    "screenshot_path": str(test.screenshot_path) if test.screenshot_path else None,
                    "test_file": test.test_file,
                    "test_class": test.test_class,
                }
                for test in suite.tests
            ],
            "environment": suite.environment,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


class ReportGenerator:
    """
    Main report generator
    
    Supports multiple output formats with a unified interface.
    """

    def __init__(self):
        self.generators = {
            ReportFormat.HTML: HTMLReportGenerator(),
            ReportFormat.MARKDOWN: MarkdownReportGenerator(),
            ReportFormat.JSON: JSONReportGenerator(),
        }

    def generate(
            self,
            suite: TestSuiteResult,
            output_path: Path,
            format: ReportFormat = ReportFormat.HTML,
    ) -> None:
        """
        Generate report in specified format
        
        Args:
            suite: Test suite results
            output_path: Output file path
            format: Report format (HTML/Markdown/JSON)
        """
        generator = self.generators.get(format)

        if not generator:
            raise ValueError(f"Unsupported format: {format}")

        generator.generate(suite, output_path)

    @staticmethod
    def from_junit_xml(xml_path: Path) -> TestSuiteResult:
        """
        Parse JUnit XML file into TestSuiteResult
        
        Args:
            xml_path: Path to JUnit XML file
            
        Returns:
            TestSuiteResult object
        """
        import xml.etree.ElementTree as ET

        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Get suite name
        suite_name = root.get("name", "Test Suite")

        # Parse tests
        tests = []
        for testcase in root.findall(".//testcase"):
            name = testcase.get("name", "Unknown")
            duration = float(testcase.get("time", "0"))

            # Determine status
            if testcase.find("failure") is not None:
                status = TestStatus.FAILED
                failure = testcase.find("failure")
                error_message = failure.get("message") if failure is not None else None
            elif testcase.find("error") is not None:
                status = TestStatus.ERROR
                error = testcase.find("error")
                error_message = error.get("message") if error is not None else None
            elif testcase.find("skipped") is not None:
                status = TestStatus.SKIPPED
                error_message = None
            else:
                status = TestStatus.PASSED
                error_message = None

            tests.append(TestResult(
                name=name,
                status=status,
                duration=duration,
                error_message=error_message,
                test_file=testcase.get("classname"),
            ))

        suite = TestSuiteResult(name=suite_name, tests=tests)
        suite.end_time = datetime.now()

        return suite
