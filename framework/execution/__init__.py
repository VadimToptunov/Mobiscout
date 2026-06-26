"""
Parallel test execution with intelligent sharding

Distributes tests across multiple workers for faster execution.
"""

from .parallel_executor import ParallelExecutor, ExecutionResult
from .test_sharding import TestSharding, ShardStrategy

__all__ = [
    'TestSharding',
    'ShardStrategy',
    'ParallelExecutor',
    'ExecutionResult',
]
