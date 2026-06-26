"""
STEP 6: API & Log Analyzer - Network и log анализ

Features:
- API call capture and correlation с UI events
- Log pattern analysis and anomaly detection
- Assertion generation для API responses
- Network trace analysis
- Request/Response matching
- Timing analysis
- Error pattern detection

Максимально гибкая архитектура без хардкода
"""

import json
import re
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional


class LogLevel(Enum):
    """Log severity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class APIMethod(Enum):
    """HTTP methods"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


@dataclass
class APICall:
    """Captured API call"""
    timestamp: datetime
    method: APIMethod
    url: str
    request_headers: Dict[str, str]
    request_body: Optional[str] = None
    response_status: Optional[int] = None
    response_headers: Optional[Dict[str, str]] = None
    response_body: Optional[str] = None
    duration_ms: Optional[float] = None
    ui_context: Optional[str] = None  # Which screen triggered it
    ui_action: Optional[str] = None  # Which action triggered it
    error: Optional[str] = None


@dataclass
class LogEntry:
    """Log entry"""
    timestamp: datetime
    level: LogLevel
    message: str
    source: str  # logcat, syslog, console, etc.
    thread: Optional[str] = None
    tag: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class APIAssertion:
    """Generated assertion for API"""
    api_call: str
    assertion_type: str  # status_code, response_contains, response_time, etc.
    expected_value: Any
    confidence: float
    reason: str


@dataclass
class LogPattern:
    """Detected log pattern"""
    pattern: str
    regex: str
    count: int
    examples: List[str]
    level: LogLevel
    is_error: bool


class APIAnalyzer:
    """
    API call analyzer

    Analyzes captured API calls for patterns, errors, and timing
    """

    def __init__(self):
        self.api_calls: List[APICall] = []
        self.correlations: Dict[str, List[APICall]] = defaultdict(list)

    def add_api_call(self, api_call: APICall):
        """Add API call to analyzer"""
        self.api_calls.append(api_call)

        # Correlate with UI context
        if api_call.ui_context:
            self.correlations[api_call.ui_context].append(api_call)

    def analyze_patterns(self) -> Dict[str, Any]:
        """
        Analyze API call patterns

        Returns:
            Analysis results with patterns, frequencies, etc.
        """
        analysis = {
            'total_calls': len(self.api_calls),
            'by_method': Counter(),
            'by_status': Counter(),
            'by_endpoint': Counter(),
            'avg_response_time': 0.0,
            'errors': [],
            'slow_calls': []
        }

        total_duration = 0.0
        duration_count = 0

        for call in self.api_calls:
            # Count by method
            analysis['by_method'][call.method.value] += 1

            # Count by status
            if call.response_status:
                analysis['by_status'][call.response_status] += 1

            # Count by endpoint
            endpoint = self._normalize_endpoint(call.url)
            analysis['by_endpoint'][endpoint] += 1

            # Calculate avg response time
            if call.duration_ms:
                total_duration += call.duration_ms
                duration_count += 1

                # Detect slow calls (>1s)
                if call.duration_ms > 1000:
                    analysis['slow_calls'].append({
                        'url': call.url,
                        'duration_ms': call.duration_ms,
                        'timestamp': call.timestamp.isoformat()
                    })

            # Detect errors
            if call.response_status and call.response_status >= 400:
                analysis['errors'].append({
                    'url': call.url,
                    'status': call.response_status,
                    'method': call.method.value,
                    'timestamp': call.timestamp.isoformat()
                })

        if duration_count > 0:
            analysis['avg_response_time'] = total_duration / duration_count

        return analysis

    def generate_assertions(self, min_confidence: float = 0.7) -> List[APIAssertion]:
        """
        Generate API assertions based on observed patterns

        Args:
            min_confidence: Minimum confidence threshold

        Returns:
            List of generated assertions
        """
        assertions = []

        # Group by endpoint
        by_endpoint = defaultdict(list)
        for call in self.api_calls:
            endpoint = self._normalize_endpoint(call.url)
            by_endpoint[endpoint].append(call)

        for endpoint, calls in by_endpoint.items():
            # Status code assertions
            status_codes = [c.response_status for c in calls if c.response_status]
            if status_codes:
                most_common = Counter(status_codes).most_common(1)[0]
                confidence = most_common[1] / len(status_codes)

                if confidence >= min_confidence:
                    assertions.append(APIAssertion(
                        api_call=endpoint,
                        assertion_type="status_code",
                        expected_value=most_common[0],
                        confidence=confidence,
                        reason=f"Observed in {most_common[1]}/{len(status_codes)} calls"
                    ))

            # Response time assertions
            durations = [c.duration_ms for c in calls if c.duration_ms]
            if durations:
                avg_duration = sum(durations) / len(durations)
                max_duration = max(durations)

                assertions.append(APIAssertion(
                    api_call=endpoint,
                    assertion_type="response_time",
                    expected_value=max_duration * 1.5,  # 50% buffer
                    confidence=0.8,
                    reason=f"Based on max observed time: {max_duration}ms"
                ))

        return assertions

    def correlate_with_ui(self, screen_id: str) -> List[APICall]:
        """Get API calls correlated with specific UI screen"""
        return self.correlations.get(screen_id, [])

    def _normalize_endpoint(self, url: str) -> str:
        """Normalize URL to endpoint pattern"""
        # Remove query params
        url = url.split('?')[0]

        # Replace IDs with placeholders
        url = re.sub(r'/\d+', '/{id}', url)
        url = re.sub(r'/[a-f0-9-]{36}', '/{uuid}', url)

        return url

    def export_har(self, output_path: Path):
        """Export API calls in HAR format"""
        har = {
            'log': {
                'version': '1.2',
                'creator': {
                    'name': 'Mobile Test Recorder',
                    'version': '1.0'
                },
                'entries': []
            }
        }

        for call in self.api_calls:
            entry = {
                'startedDateTime': call.timestamp.isoformat(),
                'time': call.duration_ms or 0,
                'request': {
                    'method': call.method.value,
                    'url': call.url,
                    'headers': [{'name': k, 'value': v} for k, v in call.request_headers.items()],
                    'bodySize': len(call.request_body) if call.request_body else 0
                },
                'response': {
                    'status': call.response_status or 0,
                    'headers': [{'name': k, 'value': v} for k, v in (call.response_headers or {}).items()],
                    'bodySize': len(call.response_body) if call.response_body else 0
                }
            }
            har['log']['entries'].append(entry)

        with open(output_path, 'w') as f:
            json.dump(har, f, indent=2)


class LogAnalyzer:
    """
    Log analyzer

    Analyzes device/application logs for patterns and errors
    """

    def __init__(self):
        self.logs: List[LogEntry] = []
        self.patterns: List[LogPattern] = []
        self.error_patterns: List[str] = [
            r'exception',
            r'error',
            r'crash',
            r'failed',
            r'timeout',
            r'null pointer',
            r'out of memory'
        ]

    def add_log(self, log: LogEntry):
        """Add log entry"""
        self.logs.append(log)

    def add_logs(self, logs: List[LogEntry]):
        """Add multiple log entries"""
        self.logs.extend(logs)

    def detect_patterns(self, min_occurrences: int = 3) -> List[LogPattern]:
        """
        Detect repeating patterns in logs

        Args:
            min_occurrences: Minimum occurrences to consider a pattern

        Returns:
            List of detected patterns
        """
        # Group similar messages
        message_groups = defaultdict(list)

        for log in self.logs:
            # Normalize message (replace numbers/IDs with placeholders)
            normalized = self._normalize_message(log.message)
            message_groups[normalized].append(log)

        patterns = []
        for normalized, logs_list in message_groups.items():
            if len(logs_list) >= min_occurrences:
                # Check if it's an error pattern
                is_error = any(re.search(pattern, normalized, re.IGNORECASE)
                               for pattern in self.error_patterns)

                pattern = LogPattern(
                    pattern=normalized,
                    regex=self._create_regex(normalized),
                    count=len(logs_list),
                    examples=[log.message for log in logs_list[:3]],
                    level=logs_list[0].level,
                    is_error=is_error
                )
                patterns.append(pattern)

        # Sort by count
        patterns.sort(key=lambda p: p.count, reverse=True)
        self.patterns = patterns

        return patterns

    def find_errors(self) -> List[LogEntry]:
        """Find error logs"""
        return [log for log in self.logs
                if log.level in (LogLevel.ERROR, LogLevel.CRITICAL)]

    def find_warnings(self) -> List[LogEntry]:
        """Find warning logs"""
        return [log for log in self.logs if log.level == LogLevel.WARNING]

    def analyze_timeframe(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """
        Analyze logs in specific timeframe

        Args:
            start: Start timestamp
            end: End timestamp

        Returns:
            Analysis results
        """
        filtered_logs = [log for log in self.logs
                         if start <= log.timestamp <= end]

        return {
            'total': len(filtered_logs),
            'by_level': Counter(log.level.value for log in filtered_logs),
            'errors': len([l for l in filtered_logs if l.level == LogLevel.ERROR]),
            'warnings': len([l for l in filtered_logs if l.level == LogLevel.WARNING])
        }

    def correlate_with_api(self, api_calls: List[APICall],
                           time_window_ms: int = 5000) -> Dict[APICall, List[LogEntry]]:
        """
        Correlate logs with API calls

        Args:
            api_calls: List of API calls
            time_window_ms: Time window for correlation (ms)

        Returns:
            Mapping of API calls to related logs
        """
        correlations = {}
        time_window = timedelta(milliseconds=time_window_ms)

        for api_call in api_calls:
            related_logs = []
            for log in self.logs:
                time_diff = abs((log.timestamp - api_call.timestamp).total_seconds() * 1000)
                if time_diff <= time_window_ms:
                    related_logs.append(log)

            if related_logs:
                correlations[api_call] = related_logs

        return correlations

    def _normalize_message(self, message: str) -> str:
        """Normalize log message for pattern matching"""
        # Replace numbers
        message = re.sub(r'\d+', '{number}', message)

        # Replace hex addresses
        message = re.sub(r'0x[0-9a-fA-F]+', '{hex}', message)

        # Replace timestamps
        message = re.sub(r'\d{2}:\d{2}:\d{2}', '{time}', message)

        # Replace UUIDs
        message = re.sub(r'[a-f0-9-]{36}', '{uuid}', message)

        return message

    def _create_regex(self, normalized: str) -> str:
        """Create regex pattern from normalized message"""
        # Escape special regex chars
        pattern = re.escape(normalized)

        # Replace placeholders with regex patterns
        pattern = pattern.replace(r'\{number\}', r'\d+')
        pattern = pattern.replace(r'\{hex\}', r'0x[0-9a-fA-F]+')
        pattern = pattern.replace(r'\{time\}', r'\d{2}:\d{2}:\d{2}')
        pattern = pattern.replace(r'\{uuid\}', r'[a-f0-9-]{36}')

        return pattern

    def export_report(self, output_path: Path):
        """Export analysis report"""
        report = {
            'summary': {
                'total_logs': len(self.logs),
                'errors': len(self.find_errors()),
                'warnings': len(self.find_warnings()),
                'patterns_found': len(self.patterns)
            },
            'patterns': [
                {
                    'pattern': p.pattern,
                    'count': p.count,
                    'is_error': p.is_error,
                    'examples': p.examples[:3]
                }
                for p in self.patterns[:10]  # Top 10
            ],
            'errors': [
                {
                    'timestamp': log.timestamp.isoformat(),
                    'message': log.message,
                    'source': log.source
                }
                for log in self.find_errors()[:20]  # First 20 errors
            ]
        }

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)


class APILogCorrelator:
    """
    Correlate API calls with logs and UI events

    Provides unified view of application behavior
    """

    def __init__(self, api_analyzer: APIAnalyzer, log_analyzer: LogAnalyzer):
        self.api_analyzer = api_analyzer
        self.log_analyzer = log_analyzer

    def correlate_all(self, time_window_ms: int = 5000) -> List[Dict[str, Any]]:
        """
        Correlate all API calls with logs

        Args:
            time_window_ms: Time window for correlation

        Returns:
            List of correlated events
        """
        correlations = []

        for api_call in self.api_analyzer.api_calls:
            # Find related logs
            time_window = timedelta(milliseconds=time_window_ms)
            related_logs = [
                log for log in self.log_analyzer.logs
                if abs((log.timestamp - api_call.timestamp).total_seconds() * 1000) <= time_window_ms
            ]

            correlations.append({
                'api_call': {
                    'method': api_call.method.value,
                    'url': api_call.url,
                    'status': api_call.response_status,
                    'duration_ms': api_call.duration_ms,
                    'ui_context': api_call.ui_context
                },
                'logs': [
                    {
                        'level': log.level.value,
                        'message': log.message,
                        'source': log.source
                    }
                    for log in related_logs
                ],
                'timestamp': api_call.timestamp.isoformat()
            })

        return correlations

    def generate_test_assertions(self) -> List[Dict[str, Any]]:
        """
        Generate test assertions combining API and log data

        Returns:
            List of assertion definitions
        """
        assertions = []

        # Get API assertions
        api_assertions = self.api_analyzer.generate_assertions()
        for assertion in api_assertions:
            assertions.append({
                'type': 'api',
                'api_call': assertion.api_call,
                'assertion': assertion.assertion_type,
                'expected': assertion.expected_value,
                'confidence': assertion.confidence
            })

        # Add log-based assertions
        error_patterns = self.log_analyzer.detect_patterns()
        for pattern in error_patterns:
            if pattern.is_error:
                assertions.append({
                    'type': 'log',
                    'pattern': pattern.pattern,
                    'assertion': 'should_not_occur',
                    'reason': f'Error pattern occurred {pattern.count} times',
                    'confidence': 0.9
                })

        return assertions


class APILogModule:
    """
    STEP 6: API & Log Analyzer - Main interface

    Unified interface for API and log analysis
    """

    def __init__(self):
        self.api_analyzer = APIAnalyzer()
        self.log_analyzer = LogAnalyzer()
        self.correlator = APILogCorrelator(self.api_analyzer, self.log_analyzer)

    def capture_api_call(self, method: str, url: str, **kwargs) -> APICall:
        """
        Capture API call

        Args:
            method: HTTP method
            url: URL
            **kwargs: Additional parameters

        Returns:
            APICall object
        """
        api_call = APICall(
            timestamp=kwargs.get('timestamp', datetime.now()),
            method=APIMethod(method.upper()),
            url=url,
            request_headers=kwargs.get('request_headers', {}),
            request_body=kwargs.get('request_body'),
            response_status=kwargs.get('response_status'),
            response_headers=kwargs.get('response_headers'),
            response_body=kwargs.get('response_body'),
            duration_ms=kwargs.get('duration_ms'),
            ui_context=kwargs.get('ui_context'),
            ui_action=kwargs.get('ui_action')
        )

        self.api_analyzer.add_api_call(api_call)
        return api_call

    def capture_log(self, level: str, message: str, source: str, **kwargs) -> LogEntry:
        """
        Capture log entry

        Args:
            level: Log level
            message: Log message
            source: Log source
            **kwargs: Additional parameters

        Returns:
            LogEntry object
        """
        log = LogEntry(
            timestamp=kwargs.get('timestamp', datetime.now()),
            level=LogLevel(level.lower()),
            message=message,
            source=source,
            thread=kwargs.get('thread'),
            tag=kwargs.get('tag'),
            metadata=kwargs.get('metadata', {})
        )

        self.log_analyzer.add_log(log)
        return log

    def analyze(self) -> Dict[str, Any]:
        """
        Perform full analysis

        Returns:
            Complete analysis results
        """
        return {
            'api_analysis': self.api_analyzer.analyze_patterns(),
            'log_analysis': {
                'patterns': [
                    {'pattern': p.pattern, 'count': p.count, 'is_error': p.is_error}
                    for p in self.log_analyzer.detect_patterns()
                ],
                'errors': len(self.log_analyzer.find_errors()),
                'warnings': len(self.log_analyzer.find_warnings())
            },
            'correlations': len(self.correlator.correlate_all()),
            'assertions': self.correlator.generate_test_assertions()
        }

    def export_reports(self, output_dir: Path):
        """Export all reports"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Export API HAR
        self.api_analyzer.export_har(output_dir / 'api_calls.har')

        # Export log report
        self.log_analyzer.export_report(output_dir / 'log_analysis.json')

        # Export correlations
        correlations = self.correlator.correlate_all()
        with open(output_dir / 'correlations.json', 'w') as f:
            json.dump(correlations, f, indent=2)
