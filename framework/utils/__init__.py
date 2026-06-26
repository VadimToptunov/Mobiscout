"""
Utilities package for the Mobile Test Recorder framework.

This package provides common utilities used across the framework:
- logger: Structured logging with Rich formatting
- validator: Input validation utilities
- sanitizer: Code identifier sanitization
- file_utils: File operation helpers
- error_handling: Comprehensive error handling
"""

from .error_handling import (
    RecorderError,
    ValidationError,
    AnalysisError,
    GenerationError,
    IntegrationError,
    handle_cli_errors,
    safe_file_operation,
    validate_and_raise,
)
from .logger import get_logger, setup_logging
from .sanitizer import sanitize_identifier, sanitize_class_name
from .validator import validate_path, validate_project_structure

__all__ = [
    "get_logger",
    "setup_logging",
    "validate_path",
    "validate_project_structure",
    "sanitize_identifier",
    "sanitize_class_name",
    "RecorderError",
    "ValidationError",
    "AnalysisError",
    "GenerationError",
    "IntegrationError",
    "handle_cli_errors",
    "safe_file_operation",
    "validate_and_raise",
]
