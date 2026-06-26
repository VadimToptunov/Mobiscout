"""
Parallel test executor

Executes tests in parallel across multiple workers/devices.
"""

import concurrent.futures
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Callable

from .test_sharding import TestCase, TestShard


class TestStatus(Enum):
    """Test execution status"""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """Result of test execution"""
    test: TestCase
    status: TestStatus
    duration: float  # seconds
    output: str = ""
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ShardResult:
    """Result of shard execution"""
    shard_id: int
    test_results: List[ExecutionResult]
    total_duration: float
    worker_id: Optional[str] = None

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.test_results if r.status == TestStatus.PASSED)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.test_results if r.status == TestStatus.FAILED)

    @property
    def total_count(self) -> int:
        return len(self.test_results)


class ParallelExecutor:
    """
    Executes tests in parallel across multiple workers
    """

    def __init__(
            self,
            max_workers: int = 4,
            pytest_args: List[str] = None
    ):
        """
        Initialize parallel executor

        Args:
            max_workers: Maximum number of parallel workers
            pytest_args: Additional arguments for pytest
        """
        self.max_workers = max_workers
        self.pytest_args = pytest_args or []

    def execute_shards(
            self,
            shards: List[TestShard],
            project_root: Path,
            progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[ShardResult]:
        """
        Execute test shards in parallel

        Args:
            shards: List of test shards
            project_root: Project root directory
            progress_callback: Callback for progress updates (completed, total)

        Returns:
            List of shard results
        """
        results = []
        completed = 0
        total = len(shards)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all shards
            future_to_shard = {
                executor.submit(self._execute_shard, shard, project_root): shard
                for shard in shards
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_shard):
                shard = future_to_shard[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total)

                except Exception as e:
                    print(f"Shard {shard.shard_id} failed with exception: {e}")
                    # Create error result
                    results.append(ShardResult(
                        shard_id=shard.shard_id,
                        test_results=[],
                        total_duration=0,
                        worker_id=None
                    ))
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total)

        return sorted(results, key=lambda r: r.shard_id)

    def _execute_shard(self, shard: TestShard, project_root: Path) -> ShardResult:
        """Execute a single shard"""
        start_time = time.time()
        test_results = []

        # Build pytest command
        # test_files =  # Unused list(set(test.file for test in shard.tests))
        # test_names =  # Unused [test.full_name for test in shard.tests]

        # Execute tests
        for test in shard.tests:
            result = self._execute_test(test, project_root)
            test_results.append(result)

        total_duration = time.time() - start_time

        return ShardResult(
            shard_id=shard.shard_id,
            test_results=test_results,
            total_duration=total_duration
        )

    def _execute_test(self, test: TestCase, project_root: Path) -> ExecutionResult:
        """Execute a single test"""
        start_time = time.time()

        # Build pytest command for specific test
        cmd = [
                  'pytest',
                  str(test.file),
                  '-k', test.name,
                  '--tb=short',
                  '-v'
              ] + self.pytest_args

        try:
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per test
            )

            duration = time.time() - start_time

            # Determine status from exit code
            if result.returncode == 0:
                status = TestStatus.PASSED
                error_message = None
            elif result.returncode == 5:  # pytest: no tests collected
                status = TestStatus.SKIPPED
                error_message = "No tests collected"
            else:
                status = TestStatus.FAILED
                error_message = result.stderr or "Test failed"

            return ExecutionResult(
                test=test,
                status=status,
                duration=duration,
                output=result.stdout,
                error_message=error_message
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                test=test,
                status=TestStatus.ERROR,
                duration=300.0,
                error_message="Test timeout (5 minutes)"
            )

        except Exception as e:
            return ExecutionResult(
                test=test,
                status=TestStatus.ERROR,
                duration=time.time() - start_time,
                error_message=f"Execution error: {e}"
            )

    def aggregate_results(self, shard_results: List[ShardResult]) -> Dict:
        """Aggregate results from all shards"""
        all_results = []
        for shard_result in shard_results:
            all_results.extend(shard_result.test_results)

        total_duration = sum(sr.total_duration for sr in shard_results)

        passed = sum(1 for r in all_results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in all_results if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in all_results if r.status == TestStatus.SKIPPED)
        errors = sum(1 for r in all_results if r.status == TestStatus.ERROR)

        return {
            'total_tests': len(all_results),
            'passed': passed,
            'failed': failed,
            'skipped': skipped,
            'errors': errors,
            'total_duration': total_duration,
            'pass_rate': (passed / len(all_results) * 100) if all_results else 0,
            'parallelization_speedup': self._calculate_speedup(all_results, total_duration)
        }

    def _calculate_speedup(self, results: List[ExecutionResult], parallel_duration: float) -> float:
        """Calculate speedup from parallelization"""
        if not results or parallel_duration == 0:
            return 1.0

        sequential_duration = sum(r.duration for r in results)
        return sequential_duration / parallel_duration if parallel_duration > 0 else 1.0

    def generate_summary(self, shard_results: List[ShardResult]) -> str:
        """Generate execution summary"""
        aggregated = self.aggregate_results(shard_results)

        summary = "=" * 80 + "\n"
        summary += "PARALLEL EXECUTION SUMMARY\n"
        summary += "=" * 80 + "\n\n"

        summary += f"Total Tests:     {aggregated['total_tests']}\n"
        summary += f"Passed:          {aggregated['passed']} ({aggregated['pass_rate']:.1f}%)\n"
        summary += f"Failed:          {aggregated['failed']}\n"
        summary += f"Skipped:         {aggregated['skipped']}\n"
        summary += f"Errors:          {aggregated['errors']}\n"
        summary += "\n"
        summary += f"Total Duration:  {aggregated['total_duration']:.2f}s\n"
        summary += f"Speedup:         {aggregated['parallelization_speedup']:.2f}x\n"
        summary += f"Workers Used:    {len(shard_results)}\n"
        summary += "\n"

        # Per-shard breakdown
        summary += "Shard Breakdown:\n"
        for shard_result in shard_results:
            summary += f"  Shard {shard_result.shard_id}: "
            summary += f"{shard_result.passed_count}/{shard_result.total_count} passed, "
            summary += f"{shard_result.total_duration:.2f}s\n"

        summary += "\n" + "=" * 80 + "\n"

        return summary
