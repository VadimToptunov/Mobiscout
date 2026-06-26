"""
Test sharding for parallel execution

Divides tests into balanced shards for parallel execution.
"""

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any


class ShardStrategy(Enum):
    """Strategy for sharding tests"""
    ROUND_ROBIN = "round_robin"  # Simple round-robin distribution
    FILE_BASED = "file_based"  # Group by file
    DURATION_BASED = "duration_based"  # Balance by historical duration
    HASH_BASED = "hash_based"  # Consistent hashing


@dataclass
class TestCase:
    """Represents a test case"""
    file: Path
    name: str
    estimated_duration: float = 1.0  # seconds

    @property
    def full_name(self) -> str:
        return f"{self.file}::{self.name}"

    def __hash__(self):
        return hash((self.file, self.name))


@dataclass
class TestShard:
    """Represents a shard of tests"""
    shard_id: int
    total_shards: int
    tests: List[TestCase]

    @property
    def estimated_duration(self) -> float:
        return sum(test.estimated_duration for test in self.tests)

    @property
    def test_count(self) -> int:
        return len(self.tests)


class TestSharding:
    """
    Divides tests into balanced shards for parallel execution
    """

    def __init__(self, duration_history: Dict[str, float] = None):
        """
        Initialize test sharding

        Args:
            duration_history: Historical test durations (test_name -> seconds)
        """
        self.duration_history = duration_history or {}

    def create_shards(
            self,
            tests: List[TestCase],
            num_shards: int,
            strategy: ShardStrategy = ShardStrategy.DURATION_BASED
    ) -> List[TestShard]:
        """
        Create test shards

        Args:
            tests: List of test cases
            num_shards: Number of shards to create
            strategy: Sharding strategy

        Returns:
            List of test shards
        """
        if num_shards <= 0:
            raise ValueError("num_shards must be positive")

        if num_shards >= len(tests):
            # One test per shard
            return [
                TestShard(shard_id=i, total_shards=num_shards, tests=[test])
                for i, test in enumerate(tests)
            ]

        if strategy == ShardStrategy.ROUND_ROBIN:
            return self._shard_round_robin(tests, num_shards)
        elif strategy == ShardStrategy.FILE_BASED:
            return self._shard_by_file(tests, num_shards)
        elif strategy == ShardStrategy.DURATION_BASED:
            return self._shard_by_duration(tests, num_shards)
        elif strategy == ShardStrategy.HASH_BASED:
            return self._shard_by_hash(tests, num_shards)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _shard_round_robin(self, tests: List[TestCase], num_shards: int) -> List[TestShard]:
        """Simple round-robin distribution"""
        shards = [TestShard(shard_id=i, total_shards=num_shards, tests=[])
                  for i in range(num_shards)]

        for i, test in enumerate(tests):
            shard_id = i % num_shards
            shards[shard_id].tests.append(test)

        return shards

    def _shard_by_file(self, tests: List[TestCase], num_shards: int) -> List[TestShard]:
        """Group tests by file, distribute files across shards"""
        # Group tests by file
        by_file: Dict[Path, List[TestCase]] = {}
        for test in tests:
            if test.file not in by_file:
                by_file[test.file] = []
            by_file[test.file].append(test)

        # Sort files by total estimated duration (descending)
        files_sorted = sorted(
            by_file.items(),
            key=lambda x: sum(t.estimated_duration for t in x[1]),
            reverse=True
        )

        # Initialize shards
        shards = [TestShard(shard_id=i, total_shards=num_shards, tests=[])
                  for i in range(num_shards)]

        # Assign files to shards (greedy algorithm - smallest duration first)
        for file_path, file_tests in files_sorted:
            # Find shard with smallest current duration
            shard = min(shards, key=lambda s: s.estimated_duration)
            shard.tests.extend(file_tests)

        return shards

    def _shard_by_duration(self, tests: List[TestCase], num_shards: int) -> List[TestShard]:
        """Balance shards by estimated duration"""
        # Update durations from history
        for test in tests:
            historical_duration = self.duration_history.get(test.full_name)
            if historical_duration:
                test.estimated_duration = historical_duration

        # Sort tests by duration (descending)
        tests_sorted = sorted(tests, key=lambda t: t.estimated_duration, reverse=True)

        # Initialize shards
        shards = [TestShard(shard_id=i, total_shards=num_shards, tests=[])
                  for i in range(num_shards)]

        # Assign tests to shards (greedy - smallest duration first)
        for test in tests_sorted:
            shard = min(shards, key=lambda s: s.estimated_duration)
            shard.tests.append(test)

        return shards

    def _shard_by_hash(self, tests: List[TestCase], num_shards: int) -> List[TestShard]:
        """Consistent hashing for stable shard assignment"""
        shards = [TestShard(shard_id=i, total_shards=num_shards, tests=[])
                  for i in range(num_shards)]

        for test in tests:
            # Hash test name to determine shard
            test_hash = hashlib.md5(test.full_name.encode()).hexdigest()
            shard_id = int(test_hash, 16) % num_shards
            shards[shard_id].tests.append(test)

        return shards

    def optimize_shards(self, shards: List[TestShard], max_imbalance: float = 0.2) -> List[TestShard]:
        """
        Optimize shard balance by redistributing tests

        Args:
            shards: List of shards to optimize
            max_imbalance: Maximum acceptable imbalance (0.2 = 20%)

        Returns:
            Optimized shards
        """
        if not shards:
            return shards

        # Calculate average duration
        total_duration = sum(s.estimated_duration for s in shards)
        avg_duration = total_duration / len(shards)

        # Check if optimization needed
        max_duration = max(s.estimated_duration for s in shards)
        min_duration = min(s.estimated_duration for s in shards)

        if avg_duration == 0 or (max_duration - min_duration) / avg_duration <= max_imbalance:
            return shards  # Already balanced

        # Simple rebalancing: move tests from heaviest to lightest
        # (In production, use more sophisticated algorithms)
        iterations = 0
        max_iterations = 100

        while iterations < max_iterations:
            heaviest = max(shards, key=lambda s: s.estimated_duration)
            lightest = min(shards, key=lambda s: s.estimated_duration)

            if (heaviest.estimated_duration - lightest.estimated_duration) / avg_duration <= max_imbalance:
                break

            # Move shortest test from heaviest to lightest
            if heaviest.tests:
                test_to_move = min(heaviest.tests, key=lambda t: t.estimated_duration)
                heaviest.tests.remove(test_to_move)
                lightest.tests.append(test_to_move)

            iterations += 1

        return shards

    def get_shard_statistics(self, shards: List[TestShard]) -> Dict[str, Any]:
        """Get statistics about shards"""
        if not shards:
            return {}

        durations = [s.estimated_duration for s in shards]
        counts = [s.test_count for s in shards]

        total_duration = sum(durations)
        avg_duration = total_duration / len(shards) if shards else 0

        return {
            'total_shards': len(shards),
            'total_tests': sum(counts),
            'total_estimated_duration': total_duration,
            'average_shard_duration': avg_duration,
            'min_shard_duration': min(durations) if durations else 0,
            'max_shard_duration': max(durations) if durations else 0,
            'duration_std_dev': self._std_dev(durations),
            'imbalance_ratio': (max(durations) - min(durations)) / avg_duration if avg_duration > 0 else 0,
            'average_tests_per_shard': sum(counts) / len(shards) if shards else 0,
        }

    def _std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if not values:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
