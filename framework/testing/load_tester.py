"""
Load Testing - Stress testing and performance profiling
"""

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from framework.devices.device_manager import DeviceManager
from framework.execution.test_runner import TestRunner


@dataclass
class LoadProfile:
    """Load testing profile configuration"""
    name: str
    description: str
    virtual_users: int
    duration_seconds: int
    ramp_up_seconds: int = 0
    think_time_seconds: float = 0.5
    iterations: Optional[int] = None


@dataclass
class LoadTestConfig:
    """Configuration for load testing"""
    test_path: Path
    profile: LoadProfile
    devices: List[str] = field(default_factory=list)
    max_workers: int = 10
    timeout_seconds: int = 300
    fail_fast: bool = False
    collect_metrics: bool = True
    output_dir: Optional[Path] = None


@dataclass
class LoadTestResult:
    """Results from a load test"""
    profile_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    error_tests: int
    total_requests: int
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p50_response_time: float
    p95_response_time: float
    p99_response_time: float
    throughput: float  # tests per second
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "profile_name": self.profile_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": self.duration_seconds,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "skipped_tests": self.skipped_tests,
            "error_tests": self.error_tests,
            "total_requests": self.total_requests,
            "avg_response_time": self.avg_response_time,
            "min_response_time": self.min_response_time,
            "max_response_time": self.max_response_time,
            "p50_response_time": self.p50_response_time,
            "p95_response_time": self.p95_response_time,
            "p99_response_time": self.p99_response_time,
            "throughput": self.throughput,
            "errors": self.errors,
            "metrics": self.metrics,
        }


class LoadTester:
    """Load testing and stress testing"""

    # Predefined load profiles
    PROFILES = {
        "smoke": LoadProfile(
            name="Smoke Test",
            description="Quick sanity check with 1 user",
            virtual_users=1,
            duration_seconds=60,
            ramp_up_seconds=0,
        ),
        "light": LoadProfile(
            name="Light Load",
            description="Light load with 5 concurrent users",
            virtual_users=5,
            duration_seconds=300,
            ramp_up_seconds=30,
        ),
        "medium": LoadProfile(
            name="Medium Load",
            description="Medium load with 20 concurrent users",
            virtual_users=20,
            duration_seconds=600,
            ramp_up_seconds=60,
        ),
        "heavy": LoadProfile(
            name="Heavy Load",
            description="Heavy load with 50 concurrent users",
            virtual_users=50,
            duration_seconds=900,
            ramp_up_seconds=120,
        ),
        "stress": LoadProfile(
            name="Stress Test",
            description="Stress test with 100 concurrent users",
            virtual_users=100,
            duration_seconds=1800,
            ramp_up_seconds=300,
        ),
        "spike": LoadProfile(
            name="Spike Test",
            description="Sudden spike with 50 users, no ramp-up",
            virtual_users=50,
            duration_seconds=300,
            ramp_up_seconds=0,
        ),
    }

    def __init__(self, config: LoadTestConfig) -> None:
        self.config = config
        self.device_manager = DeviceManager()
        self.results: List[Dict[str, Any]] = []
        self.response_times: List[float] = []

    def run(self, progress_callback: Optional[Callable[[str], None]] = None) -> LoadTestResult:
        """Run load test"""
        start_time = datetime.now()
        profile = self.config.profile

        if progress_callback:
            progress_callback(f"Starting load test: {profile.name}")
            progress_callback(f"Virtual users: {profile.virtual_users}")
            progress_callback(f"Duration: {profile.duration_seconds}s")

        # Calculate user spawn rate
        if profile.ramp_up_seconds > 0:
            spawn_delay = profile.ramp_up_seconds / profile.virtual_users
        else:
            spawn_delay = 0

        # Run load test with thread pool
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = []

            for user_id in range(profile.virtual_users):
                # Delay spawning users during ramp-up
                if spawn_delay > 0:
                    time.sleep(spawn_delay)

                future = executor.submit(
                    self._run_user_session,
                    user_id=user_id,
                    start_time=start_time,
                    progress_callback=progress_callback,
                )
                futures.append(future)

                # Check if we should stop early
                if self.config.fail_fast and self._has_critical_errors():
                    if progress_callback:
                        progress_callback("Critical errors detected, stopping test")
                    break

            # Wait for all users to complete
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=self.config.timeout_seconds)
                    self.results.append(result)
                except (TimeoutError, RuntimeError, OSError, ValueError) as e:
                    self.results.append({
                        "success": False,
                        "error": str(e),
                        "response_time": 0,
                    })

        end_time = datetime.now()

        # Generate final results
        return self._generate_results(start_time, end_time)

    def _run_user_session(
            self,
            user_id: int,
            start_time: datetime,
            progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Run a single user session"""
        profile = self.config.profile
        session_results: List[Dict[str, Any]] = []
        iteration = 0

        while True:
            # Check if we should stop
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed >= profile.duration_seconds:
                break

            if profile.iterations and iteration >= profile.iterations:
                break

            # Run test
            test_start = time.time()
            try:
                success = self._execute_test(user_id)
                test_duration = time.time() - test_start
                self.response_times.append(test_duration)

                session_results.append({
                    "success": success,
                    "response_time": test_duration,
                    "iteration": iteration,
                })

                if progress_callback:
                    progress_callback(
                        f"User {user_id} - Iteration {iteration}: "
                        f"{'PASS' if success else 'FAIL'} ({test_duration:.2f}s)"
                    )
            except (RuntimeError, OSError, ValueError, AttributeError) as e:
                test_duration = time.time() - test_start
                session_results.append({
                    "success": False,
                    "error": str(e),
                    "response_time": test_duration,
                    "iteration": iteration,
                })

            # Think time between iterations
            if profile.think_time_seconds > 0:
                time.sleep(profile.think_time_seconds)

            iteration += 1

        return {
            "user_id": user_id,
            "iterations": iteration,
            "results": session_results,
        }

    def _execute_test(self, user_id: int) -> bool:
        """Execute a single test"""
        # Get available device
        devices = self.device_manager.get_all_devices()
        if not devices:
            raise RuntimeError("No devices available")

        device = devices[user_id % len(devices)]

        # Run test
        runner = TestRunner()
        test_path = Path(self.config.test_path) if self.config.test_path else None
        result = runner.run_test(
            test_name=f"load_test_{user_id}",
            test_path=test_path
        )

        if result is None:
            return False
        from framework.execution.test_runner import TestResultStatus
        return result.status == TestResultStatus.PASSED

    def _has_critical_errors(self) -> bool:
        """Check if there are critical errors"""
        if len(self.results) < 10:
            return False

        # Check last 10 results
        recent = self.results[-10:]
        failed = sum(1 for r in recent if not r.get("success", True))

        # More than 50% failures = critical
        return failed > 5

    def _generate_results(self, start_time: datetime, end_time: datetime) -> LoadTestResult:
        """Generate final test results"""
        duration = (end_time - start_time).total_seconds()

        # Count results
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        errors = []

        for user_result in self.results:
            if "results" in user_result:
                for test_result in user_result["results"]:
                    total_tests += 1
                    if test_result.get("success", False):
                        passed_tests += 1
                    else:
                        failed_tests += 1
                        if "error" in test_result:
                            errors.append({
                                "user_id": user_result.get("user_id"),
                                "iteration": test_result.get("iteration"),
                                "error": test_result["error"],
                            })

        # Calculate response time statistics
        if self.response_times:
            avg_response = statistics.mean(self.response_times)
            min_response = min(self.response_times)
            max_response = max(self.response_times)
            sorted_times = sorted(self.response_times)
            p50 = sorted_times[int(len(sorted_times) * 0.50)]
            p95 = sorted_times[int(len(sorted_times) * 0.95)]
            p99 = sorted_times[int(len(sorted_times) * 0.99)]
        else:
            avg_response = min_response = max_response = p50 = p95 = p99 = 0

        throughput = total_tests / duration if duration > 0 else 0

        return LoadTestResult(
            profile_name=self.config.profile.name,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=0,
            error_tests=len(errors),
            total_requests=total_tests,
            avg_response_time=avg_response,
            min_response_time=min_response,
            max_response_time=max_response,
            p50_response_time=p50,
            p95_response_time=p95,
            p99_response_time=p99,
            throughput=throughput,
            errors=errors,
        )

    def save_results(self, result: LoadTestResult, output_path: Path) -> None:
        """Save results to file"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

    @classmethod
    def get_profile(cls, profile_name: str) -> LoadProfile:
        """Get predefined load profile"""
        if profile_name not in cls.PROFILES:
            raise ValueError(f"Unknown profile: {profile_name}")
        return cls.PROFILES[profile_name]

    @classmethod
    def list_profiles(cls) -> List[LoadProfile]:
        """List all predefined profiles"""
        return list(cls.PROFILES.values())
