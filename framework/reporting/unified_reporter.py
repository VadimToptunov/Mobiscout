"""
Unified test reporter

Aggregates test results from multiple sources and generates comprehensive reports.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional


class ReportFormat(Enum):
    """Supported report formats"""

    HTML = "html"
    ALLURE = "allure"
    JUNIT = "junit"
    JSON = "json"


@dataclass
class TestResult:
    """Individual test result"""

    name: str
    status: str  # passed, failed, skipped
    duration: float
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    platform: Optional[str] = None
    device: Optional[str] = None
    screenshots: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.screenshots is None:
            self.screenshots = []


@dataclass
class TestSuite:
    """Test suite results"""

    name: str
    tests: List[TestResult]
    timestamp: str
    duration: float
    platform: Optional[str] = None

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for t in self.tests if t.status == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for t in self.tests if t.status == "skipped")

    @property
    def total(self) -> int:
        return len(self.tests)

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100


class UnifiedReporter:
    """
    Unified test reporter supporting multiple formats
    """

    def __init__(self) -> None:
        self.suites: List[TestSuite] = []

    def add_suite(self, suite: TestSuite) -> None:
        """Add a test suite to the report"""
        self.suites.append(suite)

    def load_from_junit(self, junit_path: Path) -> None:
        """Load test results from JUnit XML"""
        from .junit_parser import JUnitParser

        parser = JUnitParser()
        suite = parser.parse(junit_path)
        self.add_suite(suite)

    def load_from_directory(self, directory: Path) -> None:
        """Load all JUnit XML files from directory"""
        for junit_file in directory.rglob("junit*.xml"):
            try:
                self.load_from_junit(junit_file)
            except Exception as e:
                print(f"Warning: Failed to parse {junit_file}: {e}")

    def generate_report(
            self, output_path: Path, format: ReportFormat = ReportFormat.HTML, title: str = "Test Report"
    ) -> None:
        """
        Generate test report

        Args:
            output_path: Output file path
            format: Report format
            title: Report title
        """
        if format == ReportFormat.HTML:
            self._generate_html_report(output_path, title)
        elif format == ReportFormat.JSON:
            self._generate_json_report(output_path)
        elif format == ReportFormat.ALLURE:
            self._generate_allure_report(output_path)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_html_report(self, output_path: Path, title: str) -> None:
        """Generate HTML report"""
        total_tests = sum(suite.total for suite in self.suites)
        total_passed = sum(suite.passed for suite in self.suites)
        total_failed = sum(suite.failed for suite in self.suites)
        total_skipped = sum(suite.skipped for suite in self.suites)
        total_duration = sum(suite.duration for suite in self.suites)

        pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
        }}
        .header h1 {{
            font-size: 32px;
            margin-bottom: 10px;
        }}
        .header .timestamp {{
            opacity: 0.9;
            font-size: 14px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f7fafc;
        }}
        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .summary-card .value {{
            font-size: 36px;
            font-weight: bold;
            margin: 10px 0;
        }}
        .summary-card .label {{
            color: #718096;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .passed {{ color: #48bb78; }}
        .failed {{ color: #f56565; }}
        .skipped {{ color: #ed8936; }}
        .duration {{ color: #4299e1; }}
        .progress-bar {{
            height: 8px;
            background: #e2e8f0;
            border-radius: 4px;
            overflow: hidden;
            margin: 20px 30px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #48bb78, #38a169);
            transition: width 0.3s ease;
        }}
        .suites {{
            padding: 30px;
        }}
        .suite {{
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .suite-header {{
            background: #f7fafc;
            padding: 20px;
            border-bottom: 1px solid #e2e8f0;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .suite-header:hover {{
            background: #edf2f7;
        }}
        .suite-title {{
            font-size: 18px;
            font-weight: 600;
            color: #2d3748;
        }}
        .suite-stats {{
            display: flex;
            gap: 15px;
            font-size: 14px;
        }}
        .tests {{
            display: none;
        }}
        .tests.expanded {{
            display: block;
        }}
        .test {{
            padding: 15px 20px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .test:last-child {{
            border-bottom: none;
        }}
        .test-name {{
            flex: 1;
            color: #2d3748;
        }}
        .test-status {{
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .test-status.passed {{
            background: #c6f6d5;
            color: #22543d;
        }}
        .test-status.failed {{
            background: #fed7d7;
            color: #742a2a;
        }}
        .test-status.skipped {{
            background: #feebc8;
            color: #7c2d12;
        }}
        .test-duration {{
            color: #718096;
            font-size: 14px;
            margin-left: 15px;
            min-width: 60px;
            text-align: right;
        }}
        .error-message {{
            padding: 15px 20px;
            background: #fff5f5;
            border-left: 4px solid #f56565;
            margin: 0 20px 15px 20px;
            color: #742a2a;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            word-break: break-word;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>

        <div class="summary">
            <div class="summary-card">
                <div class="label">Total Tests</div>
                <div class="value">{total_tests}</div>
            </div>
            <div class="summary-card">
                <div class="label">Passed</div>
                <div class="value passed">{total_passed}</div>
            </div>
            <div class="summary-card">
                <div class="label">Failed</div>
                <div class="value failed">{total_failed}</div>
            </div>
            <div class="summary-card">
                <div class="label">Skipped</div>
                <div class="value skipped">{total_skipped}</div>
            </div>
            <div class="summary-card">
                <div class="label">Duration</div>
                <div class="value duration">{total_duration:.2f}s</div>
            </div>
            <div class="summary-card">
                <div class="label">Pass Rate</div>
                <div class="value" style="color: {'#48bb78' if pass_rate >= 80 else '#f56565'}">{pass_rate:.1f}%</div>
            </div>
        </div>

        <div class="progress-bar">
            <div class="progress-fill" style="width: {pass_rate}%"></div>
        </div>

        <div class="suites">
"""

        # Add each test suite
        for suite in self.suites:
            html_content += """
            <div class="suite">
                <div class="suite-header" onclick="toggleSuite(this)">
                    <div class="suite-title">{suite.name}</div>
                    <div class="suite-stats">
                        <span class="passed">{suite.passed} passed</span>
                        <span class="failed">{suite.failed} failed</span>
                        <span class="skipped">{suite.skipped} skipped</span>
                        <span class="duration">{suite.duration:.2f}s</span>
                    </div>
                </div>
                <div class="tests">
"""

            # Add tests
            for test in suite.tests:
                html_content += """
                    <div class="test">
                        <div class="test-name">{test.name}</div>
                        <div class="test-duration">{test.duration:.2f}s</div>
                        <div class="test-status {test.status}">{test.status}</div>
                    </div>
"""
                if test.error_message:
                    html_content += """
                    <div class="error-message">{test.error_message}</div>
"""

            html_content += """
                </div>
            </div>
"""

        html_content += """
        </div>
    </div>

    <script>
        function toggleSuite(header) {
            const tests = header.nextElementSibling;
            tests.classList.toggle('expanded');
        }
    </script>
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content)
        print(f"✓ HTML report generated: {output_path}")

    def _generate_json_report(self, output_path: Path) -> None:
        """Generate JSON report"""
        report_data = {
            "generated": datetime.now().isoformat(),
            "summary": {
                "total": sum(s.total for s in self.suites),
                "passed": sum(s.passed for s in self.suites),
                "failed": sum(s.failed for s in self.suites),
                "skipped": sum(s.skipped for s in self.suites),
                "duration": sum(s.duration for s in self.suites),
            },
            "suites": [
                {
                    "name": suite.name,
                    "platform": suite.platform,
                    "timestamp": suite.timestamp,
                    "duration": suite.duration,
                    "tests": [
                        {
                            "name": test.name,
                            "status": test.status,
                            "duration": test.duration,
                            "platform": test.platform,
                            "device": test.device,
                            "error_message": test.error_message,
                        }
                        for test in suite.tests
                    ],
                }
                for suite in self.suites
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report_data, indent=2))
        print(f"✓ JSON report generated: {output_path}")

    def _generate_allure_report(self, output_path: Path) -> None:
        """Generate Allure-compatible results"""
        from .allure_generator import AllureGenerator

        generator = AllureGenerator()
        generator.generate(self.suites, output_path)
        print(f"✓ Allure results generated: {output_path}")
