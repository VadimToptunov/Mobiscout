"""
Dashboard data models
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class TestStatus(Enum):
    """Test execution status"""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class HealingStatus(Enum):
    """Status of healed selector"""
    PENDING = "pending"  # Awaiting review
    APPROVED = "approved"  # Approved and applied
    REJECTED = "rejected"  # Rejected, keep original


@dataclass
class TestResult:
    """Single test execution result"""
    id: str
    name: str
    status: TestStatus
    duration: float  # seconds
    timestamp: datetime
    file_path: str
    error_message: Optional[str] = None

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status.value,
            'duration': self.duration,
            'timestamp': self.timestamp.isoformat(),
            'file_path': self.file_path,
            'error_message': self.error_message
        }


@dataclass
class TestHealth:
    """Health metrics for a test"""
    test_name: str
    total_runs: int
    passed: int
    failed: int
    pass_rate: float
    avg_duration: float
    is_flaky: bool
    last_failure: Optional[datetime]
    trend: str  # "improving", "stable", "degrading"

    def to_dict(self):
        return {
            'test_name': self.test_name,
            'total_runs': self.total_runs,
            'passed': self.passed,
            'failed': self.failed,
            'pass_rate': self.pass_rate,
            'avg_duration': self.avg_duration,
            'is_flaky': self.is_flaky,
            'last_failure': self.last_failure.isoformat() if self.last_failure else None,
            'trend': self.trend
        }


@dataclass
class HealedSelector:
    """Healed selector awaiting review"""
    id: str
    test_name: str
    element_name: str
    file_path: str
    old_selector_type: str
    old_selector_value: str
    new_selector_type: str
    new_selector_value: str
    confidence: float
    strategy: str
    status: HealingStatus
    timestamp: datetime
    test_runs_after: int = 0
    test_passes_after: int = 0

    @property
    def old_selector(self) -> tuple:
        return (self.old_selector_type, self.old_selector_value)

    @property
    def new_selector(self) -> tuple:
        return (self.new_selector_type, self.new_selector_value)

    def to_dict(self):
        return {
            'id': self.id,
            'test_name': self.test_name,
            'element_name': self.element_name,
            'file_path': self.file_path,
            'old_selector': {
                'type': self.old_selector_type,
                'value': self.old_selector_value
            },
            'new_selector': {
                'type': self.new_selector_type,
                'value': self.new_selector_value
            },
            'confidence': self.confidence,
            'strategy': self.strategy,
            'status': self.status.value,
            'timestamp': self.timestamp.isoformat(),
            'test_runs_after': self.test_runs_after,
            'test_passes_after': self.test_passes_after,
            'success_rate': self.test_passes_after / self.test_runs_after if self.test_runs_after > 0 else 0
        }


@dataclass
class DashboardStats:
    """Overall dashboard statistics"""
    total_tests: int
    passing_tests: int
    failing_tests: int
    flaky_tests: int
    healed_selectors_pending: int
    healed_selectors_approved: int
    avg_pass_rate: float

    def to_dict(self):
        return {
            'total_tests': self.total_tests,
            'passing_tests': self.passing_tests,
            'failing_tests': self.failing_tests,
            'flaky_tests': self.flaky_tests,
            'healed_selectors_pending': self.healed_selectors_pending,
            'healed_selectors_approved': self.healed_selectors_approved,
            'avg_pass_rate': self.avg_pass_rate
        }
