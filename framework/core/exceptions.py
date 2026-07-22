"""
Custom Exception Hierarchy for Mobiscout

STEP 7: Paid Modules Enhancement - Exception System Refactoring

This module provides a comprehensive exception hierarchy to replace
broad Exception catches throughout the codebase.
"""

from typing import Optional, Dict, Any

# ============================================================================
# Base Exceptions
# ============================================================================


class MobileTestError(Exception):
    """Base exception for all mobile test recorder errors."""

    def __init__(self, message: str, code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """
        Initialize error with context.

        Args:
            message: Human-readable error description
            code: Machine-readable error code
            details: Additional context information
        """
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for serialization."""
        return {"error": self.__class__.__name__, "message": self.message, "code": self.code, "details": self.details}


# ============================================================================
# Device & Backend Exceptions
# ============================================================================


class DeviceError(MobileTestError):
    """Base class for device-related errors."""


class DeviceNotFoundError(DeviceError):
    """Device not found or not connected."""


class DeviceOfflineError(DeviceError):
    """Device is offline or unreachable."""


class DeviceConnectionError(DeviceError):
    """Failed to establish connection with device."""


class BackendError(MobileTestError):
    """Base class for automation backend errors."""


class BackendNotAvailableError(BackendError):
    """Automation backend not installed or not running."""


class SessionError(BackendError):
    """Error managing automation session."""


class SessionNotFoundError(SessionError):
    """Automation session not found."""


# ============================================================================
# Element & Selector Exceptions
# ============================================================================


class ElementError(MobileTestError):
    """Base class for element-related errors."""


class ElementNotFoundError(ElementError):
    """Element not found with given selector."""


class ElementNotInteractableError(ElementError):
    """Element exists but cannot be interacted with."""


class SelectorError(MobileTestError):
    """Base class for selector-related errors."""


class InvalidSelectorError(SelectorError):
    """Selector syntax is invalid."""


class SelectorTimeoutError(SelectorError):
    """Timeout waiting for selector to match."""


# ============================================================================
# Analysis & ML Exceptions
# ============================================================================


class AnalysisError(MobileTestError):
    """Base class for analysis errors."""


class ASTParsingError(AnalysisError):
    """Failed to parse AST."""


class SecurityViolationError(AnalysisError):
    """Security vulnerability detected."""


class AccessibilityViolationError(AnalysisError):
    """Accessibility issue detected."""


class MLError(MobileTestError):
    """Base class for ML-related errors."""


class ModelNotFoundError(MLError):
    """ML model not found or not loaded."""


class ModelNotTrainedError(MLError):
    """ML model not trained yet."""


class PredictionError(MLError):
    """Error during ML prediction."""


class TrainingError(MLError):
    """Error during ML model training."""


# ============================================================================
# Configuration & License Exceptions
# ============================================================================


class ConfigurationError(MobileTestError):
    """Base class for configuration errors."""


class InvalidConfigError(ConfigurationError):
    """Configuration is invalid or malformed."""


class MissingConfigError(ConfigurationError):
    """Required configuration is missing."""


# ============================================================================
# Test Generation & Execution Exceptions
# ============================================================================


class TestGenerationError(MobileTestError):
    """Base class for test generation errors."""


class CodeGenerationError(TestGenerationError):
    """Failed to generate test code."""


class TemplateError(TestGenerationError):
    """Template rendering error."""


class ExecutionError(MobileTestError):
    """Base class for test execution errors."""


class TestFailureError(ExecutionError):
    """Test execution failed."""


class TimeoutError(ExecutionError):
    """Operation timed out."""


# ============================================================================
# Storage & I/O Exceptions
# ============================================================================


class StorageError(MobileTestError):
    """Base class for storage errors."""


class FileNotFoundError(StorageError):
    """File not found at specified path."""


class FileAccessError(StorageError):
    """Cannot access file (permissions, locked, etc.)."""


class SerializationError(StorageError):
    """Failed to serialize/deserialize data."""


class DatabaseError(StorageError):
    """Database operation failed."""


# ============================================================================
# Network & API Exceptions
# ============================================================================


class NetworkError(MobileTestError):
    """Base class for network errors."""


class ConnectionError(NetworkError):
    """Network connection failed."""


class APIError(MobileTestError):
    """Base class for API errors."""


class APIRequestError(APIError):
    """API request failed."""


class APIResponseError(APIError):
    """API returned unexpected response."""


class APITimeoutError(APIError):
    """API request timed out."""


# ============================================================================
# Security & Performance Exceptions
# ============================================================================


class PerformanceError(MobileTestError):
    """Base class for performance issues."""


class PerformanceThresholdExceededError(PerformanceError):
    """Performance metric exceeded threshold."""


class MemoryError(PerformanceError):
    """Memory usage exceeded limit."""


class FuzzingError(MobileTestError):
    """Base class for fuzzing errors."""


class InvalidInputError(FuzzingError):
    """Generated input is invalid."""


# ============================================================================
# Utility Functions
# ============================================================================


def format_error_message(error: Exception, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Format error message with context.

    Args:
        error: Exception to format
        context: Additional context information

    Returns:
        Formatted error message
    """
    if isinstance(error, MobileTestError):
        msg = f"[{error.code}] {error.message}"
        if error.details:
            msg += f"\nDetails: {error.details}"
    else:
        msg = str(error)

    if context:
        msg += f"\nContext: {context}"

    return msg


def is_retriable_error(error: Exception) -> bool:
    """
    Check if error is retriable.

    Args:
        error: Exception to check

    Returns:
        True if error can be retried
    """
    retriable_types = (DeviceConnectionError, NetworkError, TimeoutError, SessionError, ElementNotInteractableError)
    return isinstance(error, retriable_types)
