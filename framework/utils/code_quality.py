"""
Code Deduplication Utilities

STEP 7: Paid Modules Enhancement - Code Quality Refactoring

This module provides utilities to reduce code duplication identified
in inspection reports.
"""

import json
import logging
from functools import wraps
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, TypeVar, Generic

logger = logging.getLogger(__name__)

T = TypeVar('T')


# ============================================================================
# File I/O Helpers
# ============================================================================

def read_json_file(file_path: Path) -> Dict[str, Any]:
    """
    Read and parse JSON file with error handling.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If JSON is invalid
    """
    from framework.core.exceptions import FileNotFoundError as CustomFileNotFoundError, SerializationError

    if not file_path.exists():
        raise CustomFileNotFoundError(
            f"File not found: {file_path}",
            details={"path": str(file_path)}
        )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise SerializationError(
            f"Invalid JSON in file: {file_path}",
            details={"path": str(file_path), "error": str(e)}
        )


def write_json_file(file_path: Path, data: Dict[str, Any], pretty: bool = True) -> None:
    """
    Write data to JSON file with error handling.

    Args:
        file_path: Path to output file
        data: Data to serialize
        pretty: Whether to pretty-print JSON

    Raises:
        SerializationError: If data cannot be serialized
    """
    from framework.core.exceptions import SerializationError

    try:
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise SerializationError(
            f"Cannot serialize data to JSON",
            details={"path": str(file_path), "error": str(e)}
        )


def ensure_directory(directory: Path) -> Path:
    """
    Ensure directory exists, creating if necessary.

    Args:
        directory: Directory path

    Returns:
        The directory path (for chaining)
    """
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# ============================================================================
# Data Processing Helpers
# ============================================================================

def calculate_statistics(items: List[T], key: Optional[Callable[[T], Any]] = None) -> Dict[str, Any]:
    """
    Calculate statistics for a collection of items.

    Args:
        items: Items to analyze
        key: Optional function to extract numeric value from item

    Returns:
        Dictionary with count, and numeric stats if applicable
    """
    if not items:
        return {
            "count": 0,
            "total": 0,
            "min": None,
            "max": None,
            "avg": None
        }

    count = len(items)

    # Try to extract numeric values
    if key:
        try:
            values = [key(item) for item in items if key(item) is not None]
            if values:
                return {
                    "count": count,
                    "total": sum(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values)
                }
        except (TypeError, ValueError):
            pass

    return {"count": count}


def group_by(items: List[T], key: Callable[[T], str]) -> Dict[str, List[T]]:
    """
    Group items by a key function.

    Args:
        items: Items to group
        key: Function to extract grouping key from item

    Returns:
        Dictionary mapping keys to lists of items
    """
    groups: Dict[str, List[T]] = {}

    for item in items:
        group_key = key(item)
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(item)

    return groups


# ============================================================================
# Validation Helpers
# ============================================================================

def validate_file_exists(file_path: Path, file_type: str = "file") -> None:
    """
    Validate that a file exists.

    Args:
        file_path: Path to validate
        file_type: Description of file type for error message

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    from framework.core.exceptions import FileNotFoundError as CustomFileNotFoundError

    if not file_path.exists():
        raise CustomFileNotFoundError(
            f"{file_type.capitalize()} not found: {file_path}",
            details={"path": str(file_path), "type": file_type}
        )


def validate_directory(directory: Path) -> None:
    """
    Validate that a directory exists and is accessible.

    Args:
        directory: Directory path to validate

    Raises:
        FileNotFoundError: If directory doesn't exist
        FileAccessError: If directory is not accessible
    """
    from framework.core.exceptions import (
        FileNotFoundError as CustomFileNotFoundError,
        FileAccessError
    )

    if not directory.exists():
        raise CustomFileNotFoundError(
            f"Directory not found: {directory}",
            details={"path": str(directory)}
        )

    if not directory.is_dir():
        raise FileAccessError(
            f"Path is not a directory: {directory}",
            details={"path": str(directory)}
        )


# ============================================================================
# Result Reporting Helpers
# ============================================================================

class ResultCollector(Generic[T]):
    """
    Collect and summarize results from multiple operations.
    """

    def __init__(self):
        """Initialize result collector."""
        self.items: List[T] = []
        self.errors: List[Exception] = []
        self.warnings: List[str] = []

    def add_success(self, item: T) -> None:
        """
        Add successful result.

        Args:
            item: Result item
        """
        self.items.append(item)

    def add_error(self, error: Exception) -> None:
        """
        Add error.

        Args:
            error: Exception that occurred
        """
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """
        Add warning message.

        Args:
            warning: Warning message
        """
        self.warnings.append(warning)

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of collected results.

        Returns:
            Summary dictionary
        """
        return {
            "success_count": len(self.items),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "total": len(self.items) + len(self.errors)
        }

    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if any warnings occurred."""
        return len(self.warnings) > 0


def print_summary(
        title: str,
        stats: Dict[str, Any],
        verbose: bool = False
) -> None:
    """
    Print formatted summary.

    Args:
        title: Summary title
        stats: Statistics dictionary
        verbose: Whether to print detailed info
    """
    print(f"\n{'=' * 60}")
    print(f"{title}")
    print(f"{'=' * 60}")

    for key, value in stats.items():
        if isinstance(value, dict):
            print(f"\n{key}:")
            for sub_key, sub_value in value.items():
                print(f"  {sub_key}: {sub_value}")
        elif verbose or not key.startswith("_"):
            print(f"{key}: {value}")

    print(f"{'=' * 60}\n")


# ============================================================================
# Retry Decorator
# ============================================================================

def retry_on_error(
        max_attempts: int = 3,
        delay_seconds: float = 1.0,
        retriable_errors: Optional[tuple] = None
) -> Callable:
    """
    Decorator to retry function on specific errors.

    Args:
        max_attempts: Maximum number of attempts
        delay_seconds: Delay between attempts
        retriable_errors: Tuple of exception types to retry on

    Returns:
        Decorated function
    """
    import time
    from framework.core.exceptions import is_retriable_error

    if retriable_errors is None:
        # Use default retriable errors
        retriable_errors = (Exception,)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    # Check if error is retriable
                    if not (isinstance(e, retriable_errors) or is_retriable_error(e)):
                        raise

                    if attempt < max_attempts:
                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay_seconds}s..."
                        )
                        time.sleep(delay_seconds)
                    else:
                        logger.error(f"All {max_attempts} attempts failed")

            # All attempts failed
            raise last_error

        return wrapper

    return decorator


# ============================================================================
# Context Managers
# ============================================================================

from contextlib import contextmanager
from typing import Iterator


@contextmanager
def handle_errors(
        operation: str,
        raise_on_error: bool = True
) -> Iterator[ResultCollector]:
    """
    Context manager for error handling with result collection.

    Args:
        operation: Description of operation
        raise_on_error: Whether to raise exception on error

    Yields:
        ResultCollector for tracking results

    Example:
        with handle_errors("processing files") as results:
            for file in files:
                try:
                    data = process_file(file)
                    results.add_success(data)
                except Exception as e:
                    results.add_error(e)
    """
    collector = ResultCollector()

    try:
        yield collector
    except Exception as e:
        logger.error(f"Error during {operation}: {e}")
        collector.add_error(e)

        if raise_on_error:
            raise
    finally:
        # Log summary
        summary = collector.get_summary()
        logger.info(f"{operation} completed: {summary}")


# ============================================================================
# Progress Tracking
# ============================================================================

class ProgressTracker:
    """Track progress of long-running operations."""

    def __init__(self, total: int, description: str = "Processing"):
        """
        Initialize progress tracker.

        Args:
            total: Total number of items
            description: Operation description
        """
        self.total = total
        self.current = 0
        self.description = description

    def update(self, increment: int = 1) -> None:
        """
        Update progress.

        Args:
            increment: Number of items completed
        """
        self.current += increment
        percentage = (self.current / self.total * 100) if self.total > 0 else 0

        print(f"\r{self.description}: {self.current}/{self.total} ({percentage:.1f}%)", end="")

        if self.current >= self.total:
            print()  # New line when complete

    def finish(self) -> None:
        """Mark progress as complete."""
        self.current = self.total
        self.update(0)
