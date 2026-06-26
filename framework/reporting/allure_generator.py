"""
Allure report generator

Generates Allure-compatible JSON results.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from .unified_reporter import TestSuite, TestResult


class AllureGenerator:
    """
    Generator for Allure report format
    """

    def generate(self, suites: List[TestSuite], output_dir: Path):
        """
        Generate Allure JSON results

        Args:
            suites: List of test suites
            output_dir: Output directory for Allure results
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        for suite in suites:
            for test in suite.tests:
                self._generate_test_result(test, suite, output_dir)

    def _generate_test_result(self, test: TestResult, suite: TestSuite, output_dir: Path):
        """Generate Allure result for single test"""
        test_uuid = str(uuid.uuid4())

        # Map status
        status_map = {
            'passed': 'passed',
            'failed': 'failed',
            'skipped': 'skipped'
        }
        status = status_map.get(test.status, 'unknown')

        # Create Allure result
        result = {
            'uuid': test_uuid,
            'historyId': self._get_history_id(test.name),
            'name': test.name,
            'fullName': f"{suite.name}.{test.name}",
            'status': status,
            'statusDetails': {},
            'stage': 'finished',
            'start': self._get_timestamp(suite.timestamp),
            'stop': self._get_timestamp(suite.timestamp) + int(test.duration * 1000),
            'labels': [
                {'name': 'suite', 'value': suite.name},
                {'name': 'framework', 'value': 'pytest'},
                {'name': 'language', 'value': 'python'},
            ],
            'links': []
        }

        # Add platform labels if available
        if test.platform:
            result['labels'].append({'name': 'platform', 'value': test.platform})
        if test.device:
            result['labels'].append({'name': 'device', 'value': test.device})

        # Add error details if failed
        if status == 'failed' and test.error_message:
            result['statusDetails'] = {
                'message': test.error_message,
                'trace': test.stack_trace or ''
            }
        elif status == 'skipped' and test.error_message:
            result['statusDetails'] = {
                'message': test.error_message
            }

        # Add screenshots as attachments
        if test.screenshots:
            result['attachments'] = [
                {
                    'name': Path(screenshot).name,
                    'source': screenshot,
                    'type': 'image/png'
                }
                for screenshot in test.screenshots
            ]

        # Write result file
        result_file = output_dir / f'{test_uuid}-result.json'
        result_file.write_text(json.dumps(result, indent=2))

    def _get_history_id(self, test_name: str) -> str:
        """Generate consistent history ID for test"""
        import hashlib
        return hashlib.md5(test_name.encode()).hexdigest()

    def _get_timestamp(self, timestamp_str: str) -> int:
        """Convert timestamp string to milliseconds"""
        try:
            if timestamp_str:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
        except (ValueError, AttributeError):
            pass
        return int(datetime.now().timestamp() * 1000)
