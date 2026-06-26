"""
Custom Exception Hierarchy for Mobile Test Recorder

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

    def __init__(
            self,
            message: str,
            code: Optional[str] = None,
            details: Optional[Dict[str, Any]] = None
    ):
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
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "code": self.code,
            "details": self.details
        }


# ============================================================================
# Device & Backend Exceptions
# ============================================================================

class DeviceError(MobileTestError):
    """Base class for device-related errors."""
    pass


class DeviceNotFoundError(DeviceError):
    """Device not found or not connected."""
    pass


class DeviceOfflineError(DeviceError):
    """Device is offline or unreachable."""
    pass


class DeviceConnectionError(DeviceError):
    """Failed to establish connection with device."""
    pass


class BackendError(MobileTestError):
    """Base class for automation backend errors."""
    pass


class BackendNotAvailableError(BackendError):
    """Automation backend not installed or not running."""
    pass


class SessionError(BackendError):
    """Error managing automation session."""
    pass


class SessionNotFoundError(SessionError):
    """Automation session not found."""
    pass


# ============================================================================
# Element & Selector Exceptions
# ============================================================================

class ElementError(MobileTestError):
    """Base class for element-related errors."""
    pass


class ElementNotFoundError(ElementError):
    """Element not found with given selector."""
    pass


class ElementNotInteractableError(ElementError):
    """Element exists but cannot be interacted with."""
    pass


class SelectorError(MobileTestError):
    """Base class for selector-related errors."""
    pass


class InvalidSelectorError(SelectorError):
    """Selector syntax is invalid."""
    pass


class SelectorTimeoutError(SelectorError):
    """Timeout waiting for selector to match."""
    pass


# ============================================================================
# Analysis & ML Exceptions
# ============================================================================

class AnalysisError(MobileTestError):
    """Base class for analysis errors."""
    pass


class ASTParsingError(AnalysisError):
    """Failed to parse AST."""
    pass


class SecurityViolationError(AnalysisError):
    """Security vulnerability detected."""
    pass


class AccessibilityViolationError(AnalysisError):
    """Accessibility issue detected."""
    pass


class MLError(MobileTestError):
    """Base class for ML-related errors."""
    pass


class ModelNotFoundError(MLError):
    """ML model not found or not loaded."""
    pass


class ModelNotTrainedError(MLError):
    """ML model not trained yet."""
    pass


class PredictionError(MLError):
    """Error during ML prediction."""
    pass


class TrainingError(MLError):
    """Error during ML model training."""
    pass


# ============================================================================
# Configuration & License Exceptions
# ============================================================================

class ConfigurationError(MobileTestError):
    """Base class for configuration errors."""
    pass


class InvalidConfigError(ConfigurationError):
    """Configuration is invalid or malformed."""
    pass


class MissingConfigError(ConfigurationError):
    """Required configuration is missing."""
    pass


class LicenseError(MobileTestError):
    """Base class for licensing errors."""
    pass


class InvalidLicenseError(LicenseError):
    """License key is invalid or expired."""
    pass


class LicenseExpiredError(LicenseError):
    """License has expired."""
    pass


class FeatureNotLicensedError(LicenseError):
    """Feature requires paid license."""
    pass


# ============================================================================
# Test Generation & Execution Exceptions
# ============================================================================

class TestGenerationError(MobileTestError):
    """Base class for test generation errors."""
    pass


class CodeGenerationError(TestGenerationError):
    """Failed to generate test code."""
    pass


class TemplateError(TestGenerationError):
    """Template rendering error."""
    pass


class ExecutionError(MobileTestError):
    """Base class for test execution errors."""
    pass


class TestFailureError(ExecutionError):
    """Test execution failed."""
    pass


class TimeoutError(ExecutionError):
    """Operation timed out."""
    pass


# ============================================================================
# Storage & I/O Exceptions
# ============================================================================

class StorageError(MobileTestError):
    """Base class for storage errors."""
    pass


class FileNotFoundError(StorageError):
    """File not found at specified path."""
    pass


class FileAccessError(StorageError):
    """Cannot access file (permissions, locked, etc.)."""
    pass


class SerializationError(StorageError):
    """Failed to serialize/deserialize data."""
    pass


class DatabaseError(StorageError):
    """Database operation failed."""
    pass


# ============================================================================
# Network & API Exceptions
# ============================================================================

class NetworkError(MobileTestError):
    """Base class for network errors."""
    pass


class ConnectionError(NetworkError):
    """Network connection failed."""
    pass


class APIError(MobileTestError):
    """Base class for API errors."""
    pass


class APIRequestError(APIError):
    """API request failed."""
    pass


class APIResponseError(APIError):
    """API returned unexpected response."""
    pass


class APITimeoutError(APIError):
    """API request timed out."""
    pass


# ============================================================================
# Security & Performance Exceptions
# ============================================================================

class PerformanceError(MobileTestError):
    """Base class for performance issues."""
    pass


class PerformanceThresholdExceededError(PerformanceError):
    """Performance metric exceeded threshold."""
    pass


class MemoryError(PerformanceError):
    """Memory usage exceeded limit."""
    pass


class FuzzingError(MobileTestError):
    """Base class for fuzzing errors."""
    pass


class InvalidInputError(FuzzingError):
    """Generated input is invalid."""
    pass


# ============================================================================
# Utility Functions
# ============================================================================

def format_error_message(
        error: Exception,
        context: Optional[Dict[str, Any]] = None
) -> str:
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
    retriable_types = (
        DeviceConnectionError,
        NetworkError,
        TimeoutError,
        SessionError,
        ElementNotInteractableError
    )
    return isinstance(error, retriable_types)
