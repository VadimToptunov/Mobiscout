"""
Tests for Parallel Execution
"""

from pathlib import Path

import pytest

from framework.execution.parallel_executor import (
    ParallelExecutor,
    TestStatus,
    ExecutionResult,
    ShardResult,
)
from framework.execution.test_sharding import (
    TestCase,
    ShardStrategy,
    TestSharding,
)


@pytest.fixture
def sample_tests():
    """Create sample test cases"""
    return [
        TestCase(
            file=Path("test_auth.py"),
            name="test_login",
            estimated_duration=1.5,
        ),
        TestCase(
            file=Path("test_auth.py"),
            name="test_logout",
            estimated_duration=1.0,
        ),
        TestCase(
            file=Path("test_api.py"),
            name="test_get_users",
            estimated_duration=2.0,
        ),
        TestCase(
            file=Path("test_api.py"),
            name="test_create_user",
            estimated_duration=2.5,
        ),
        TestCase(
            file=Path("test_ui.py"),
            name="test_button_click",
            estimated_duration=3.0,
        ),
    ]


class TestTestSharding:
    """Test test sharding functionality"""

    def test_round_robin_sharding(self, sample_tests):
        """Test round-robin sharding strategy"""
        sharding = TestSharding()
        shards = sharding.create_shards(sample_tests, num_shards=2, strategy=ShardStrategy.ROUND_ROBIN)

        assert len(shards) == 2
        assert shards[0].shard_id == 0
        assert shards[1].shard_id == 1

        # Tests should be distributed evenly
        assert len(shards[0].tests) + len(shards[1].tests) == len(sample_tests)

    def test_balanced_sharding(self, sample_tests):
        """Test balanced sharding based on estimated duration"""
        sharding = TestSharding()
        shards = sharding.create_shards(sample_tests, num_shards=2, strategy=ShardStrategy.DURATION_BASED)

        assert len(shards) == 2

        # Calculate total duration per shard
        shard0_duration = sum(t.estimated_duration for t in shards[0].tests)
        shard1_duration = sum(t.estimated_duration for t in shards[1].tests)

        # Durations should be relatively balanced
        # (within 50% of each other)
        ratio = max(shard0_duration, shard1_duration) / min(shard0_duration, shard1_duration)
        assert ratio < 1.5

    def test_by_file_sharding(self, sample_tests):
        """Test sharding by file"""
        sharding = TestSharding()
        shards = sharding.create_shards(sample_tests, num_shards=3, strategy=ShardStrategy.FILE_BASED)

        assert len(shards) <= 3  # May be fewer if not enough files

        # Tests from same file should be in same shard
        for shard in shards:
            files = set(test.file for test in shard.tests)
            # Each shard should have tests from limited number of files
            assert len(files) <= 2

    def test_single_shard(self, sample_tests):
        """Test creating a single shard"""
        sharding = TestSharding()
        shards = sharding.create_shards(sample_tests, num_shards=1, strategy=ShardStrategy.ROUND_ROBIN)

        assert len(shards) == 1
        assert len(shards[0].tests) == len(sample_tests)

    def test_more_shards_than_tests(self, sample_tests):
        """Test creating more shards than tests"""
        sharding = TestSharding()
        shards = sharding.create_shards(sample_tests, num_shards=10, strategy=ShardStrategy.ROUND_ROBIN)

        # Should create at most as many shards as tests
        assert len(shards) <= len(sample_tests)


class TestParallelExecutor:
    """Test parallel executor functionality"""

    def test_executor_initialization(self):
        """Test executor initialization"""
        executor = ParallelExecutor(max_workers=4)

        assert executor.max_workers == 4
        assert executor.pytest_args == []

    def test_executor_with_pytest_args(self):
        """Test executor with custom pytest args"""
        executor = ParallelExecutor(max_workers=2, pytest_args=["-v", "--tb=short"])

        assert executor.max_workers == 2
        assert executor.pytest_args == ["-v", "--tb=short"]

    def test_aggregate_results_empty(self):
        """Test aggregating empty results"""
        executor = ParallelExecutor()
        results = executor.aggregate_results([])

        assert results["total_tests"] == 0
        assert results["passed"] == 0
        assert results["failed"] == 0

    def test_aggregate_results(self):
        """Test aggregating shard results"""
        executor = ParallelExecutor()

        # Create mock results
        test1 = TestCase(Path("test1.py"), "test1", 1.0)
        test2 = TestCase(Path("test2.py"), "test2", 1.0)
        test3 = TestCase(Path("test3.py"), "test3", 1.0)

        shard_results = [
            ShardResult(
                shard_id=0,
                test_results=[
                    ExecutionResult(test1, TestStatus.PASSED, 1.0, output=""),
                    ExecutionResult(test2, TestStatus.FAILED, 1.5, output=""),
                ],
                total_duration=2.5,
            ),
            ShardResult(
                shard_id=1,
                test_results=[
                    ExecutionResult(test3, TestStatus.PASSED, 2.0, output=""),
                ],
                total_duration=2.0,
            ),
        ]

        aggregated = executor.aggregate_results(shard_results)

        assert aggregated["total_tests"] == 3
        assert aggregated["passed"] == 2
        assert aggregated["failed"] == 1
        assert aggregated["skipped"] == 0
        assert aggregated["total_duration"] == 4.5
        assert aggregated["pass_rate"] == pytest.approx(66.67, rel=0.1)

    def test_generate_summary(self):
        """Test summary generation"""
        executor = ParallelExecutor()

        test1 = TestCase(Path("test1.py"), "test1", 1.0)
        test2 = TestCase(Path("test2.py"), "test2", 1.0)

        shard_results = [
            ShardResult(
                shard_id=0,
                test_results=[
                    ExecutionResult(test1, TestStatus.PASSED, 1.0, output=""),
                ],
                total_duration=1.0,
            ),
            ShardResult(
                shard_id=1,
                test_results=[
                    ExecutionResult(test2, TestStatus.PASSED, 1.0, output=""),
                ],
                total_duration=1.0,
            ),
        ]

        summary = executor.generate_summary(shard_results)

        assert "PARALLEL EXECUTION SUMMARY" in summary
        assert "Total Tests:     2" in summary
        assert "Passed:          2" in summary
        assert "Shard 0:" in summary
        assert "Shard 1:" in summary

    def test_speedup_calculation(self):
        """Test speedup calculation"""
        executor = ParallelExecutor()

        test1 = TestCase(Path("test1.py"), "test1", 2.0)
        test2 = TestCase(Path("test2.py"), "test2", 2.0)

        # If tests run sequentially: 4s
        # If tests run in parallel on 2 workers: ~2s
        # Speedup should be ~2x
        results = [
            ExecutionResult(test1, TestStatus.PASSED, 2.0, output=""),
            ExecutionResult(test2, TestStatus.PASSED, 2.0, output=""),
        ]

        speedup = executor._calculate_speedup(results, parallel_duration=2.0)

        assert speedup == pytest.approx(2.0, rel=0.1)


class TestShardResult:
    """Test ShardResult functionality"""

    def test_shard_result_properties(self):
        """Test shard result property calculations"""
        test1 = TestCase(Path("test1.py"), "test1", 1.0)
        test2 = TestCase(Path("test2.py"), "test2", 1.0)
        test3 = TestCase(Path("test3.py"), "test3", 1.0)

        shard_result = ShardResult(
            shard_id=0,
            test_results=[
                ExecutionResult(test1, TestStatus.PASSED, 1.0, output=""),
                ExecutionResult(test2, TestStatus.FAILED, 1.0, output=""),
                ExecutionResult(test3, TestStatus.PASSED, 1.0, output=""),
            ],
            total_duration=3.0,
        )

        assert shard_result.total_count == 3
        assert shard_result.passed_count == 2
        assert shard_result.failed_count == 1


class TestExecutionResult:
    """Test ExecutionResult functionality"""

    def test_execution_result_creation(self):
        """Test creating execution result"""
        test = TestCase(Path("test.py"), "test_func", 1.0)
        result = ExecutionResult(
            test=test,
            status=TestStatus.PASSED,
            duration=1.5,
            output="Test passed",
        )

        assert result.test == test
        assert result.status == TestStatus.PASSED
        assert result.duration == 1.5
        assert result.output == "Test passed"
        assert result.error_message is None

    def test_execution_result_with_error(self):
        """Test execution result with error"""
        test = TestCase(Path("test.py"), "test_func", 1.0)
        result = ExecutionResult(
            test=test,
            status=TestStatus.ERROR,
            duration=0.5,
            error_message="Connection timeout",
        )

        assert result.status == TestStatus.ERROR
        assert result.error_message == "Connection timeout"


def test_integration_sharding_and_execution(sample_tests):
    """Integration test: create shards and mock execution"""
    # Create balanced shards
    sharding = TestSharding()
    shards = sharding.create_shards(sample_tests, num_shards=2, strategy=ShardStrategy.DURATION_BASED)

    assert len(shards) == 2

    # Verify all tests are distributed
    total_tests = sum(len(shard.tests) for shard in shards)
    assert total_tests == len(sample_tests)

    # Verify no duplicates
    all_test_names = []
    for shard in shards:
        for test in shard.tests:
            all_test_names.append(test.full_name)

    assert len(all_test_names) == len(set(all_test_names))


def test_load_balancing(sample_tests):
    """Test that load balancing distributes work evenly"""
    # Create shards with balanced strategy
    sharding = TestSharding()
    shards = sharding.create_shards(sample_tests, num_shards=2, strategy=ShardStrategy.DURATION_BASED)

    durations = [sum(t.estimated_duration for t in shard.tests) for shard in shards]

    # Check that load is relatively balanced
    max_duration = max(durations)
    min_duration = min(durations)

    # Should be within 50% of each other for good load balancing
    assert max_duration / min_duration < 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
