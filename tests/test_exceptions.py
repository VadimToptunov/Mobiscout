"""
Unit Tests for Custom Exception Hierarchy

STEP 7: Paid Modules Enhancement - Exception System Tests
"""

import pytest

from framework.core.exceptions import (
    # Base
    MobileTestError,
    # Device
    DeviceError,
    DeviceNotFoundError,
    DeviceOfflineError,
    DeviceConnectionError,
    # Backend
    BackendError,
    BackendNotAvailableError,
    SessionError,
    SessionNotFoundError,
    # Element
    ElementError,
    ElementNotFoundError,
    ElementNotInteractableError,
    # Selector
    SelectorError,
    InvalidSelectorError,
    SelectorTimeoutError,
    # Analysis
    AnalysisError,
    ASTParsingError,
    SecurityViolationError,
    AccessibilityViolationError,
    # ML
    MLError,
    ModelNotFoundError,
    ModelNotTrainedError,
    PredictionError,
    TrainingError,
    # Config
    ConfigurationError,
    InvalidConfigError,
    MissingConfigError,
    # License
    LicenseError,
    InvalidLicenseError,
    LicenseExpiredError,
    FeatureNotLicensedError,
    # Test & Execution
    TimeoutError,
    # Network & API
    NetworkError,
    APIError,
    # Utility functions
    format_error_message,
    is_retriable_error
)


class TestBaseException:
    """Test MobileTestError base exception."""

    def test_basic_exception(self):
        """Test basic exception creation."""
        error = MobileTestError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.code == "MobileTestError"
        assert error.details == {}

    def test_exception_with_code(self):
        """Test exception with custom code."""
        error = MobileTestError("Test error", code="TEST001")
        assert error.code == "TEST001"

    def test_exception_with_details(self):
        """Test exception with details."""
        details = {"device_id": "emulator-5554", "attempt": 3}
        error = MobileTestError("Test error", details=details)
        assert error.details == details

    def test_to_dict(self):
        """Test exception serialization."""
        error = MobileTestError(
            "Test error",
            code="TEST001",
            details={"key": "value"}
        )
        result = error.to_dict()

        assert result["error"] == "MobileTestError"
        assert result["message"] == "Test error"
        assert result["code"] == "TEST001"
        assert result["details"] == {"key": "value"}


class TestDeviceExceptions:
    """Test device-related exceptions."""

    def test_device_not_found(self):
        """Test DeviceNotFoundError."""
        error = DeviceNotFoundError(
            "Device not found",
            details={"device_id": "unknown"}
        )
        assert isinstance(error, DeviceError)
        assert isinstance(error, MobileTestError)

    def test_device_offline(self):
        """Test DeviceOfflineError."""
        error = DeviceOfflineError("Device offline")
        assert isinstance(error, DeviceError)

    def test_device_connection(self):
        """Test DeviceConnectionError."""
        error = DeviceConnectionError("Connection failed")
        assert isinstance(error, DeviceError)


class TestBackendExceptions:
    """Test backend-related exceptions."""

    def test_backend_not_available(self):
        """Test BackendNotAvailableError."""
        error = BackendNotAvailableError(
            "Appium not running",
            details={"backend": "appium"}
        )
        assert isinstance(error, BackendError)

    def test_session_not_found(self):
        """Test SessionNotFoundError."""
        error = SessionNotFoundError(
            "Session expired",
            details={"session_id": "abc123"}
        )
        assert isinstance(error, SessionError)
        assert isinstance(error, BackendError)


class TestElementExceptions:
    """Test element-related exceptions."""

    def test_element_not_found(self):
        """Test ElementNotFoundError."""
        error = ElementNotFoundError(
            "Element not found",
            details={"selector": "//button[@id='submit']"}
        )
        assert isinstance(error, ElementError)

    def test_element_not_interactable(self):
        """Test ElementNotInteractableError."""
        error = ElementNotInteractableError(
            "Element is disabled",
            details={"element_id": "btn_123"}
        )
        assert isinstance(error, ElementError)


class TestSelectorExceptions:
    """Test selector-related exceptions."""

    def test_invalid_selector(self):
        """Test InvalidSelectorError."""
        error = InvalidSelectorError(
            "Invalid XPath syntax",
            details={"selector": "//button["}
        )
        assert isinstance(error, SelectorError)

    def test_selector_timeout(self):
        """Test SelectorTimeoutError."""
        error = SelectorTimeoutError(
            "Timeout waiting for element",
            details={"timeout": 30, "selector": "//div[@class='loading']"}
        )
        assert isinstance(error, SelectorError)


class TestAnalysisExceptions:
    """Test analysis-related exceptions."""

    def test_ast_parsing_error(self):
        """Test ASTParsingError."""
        error = ASTParsingError(
            "Invalid Python syntax",
            details={"file": "test.py", "line": 42}
        )
        assert isinstance(error, AnalysisError)

    def test_security_violation(self):
        """Test SecurityViolationError."""
        error = SecurityViolationError(
            "SQL injection detected",
            details={"severity": "critical", "location": "login.py:15"}
        )
        assert isinstance(error, AnalysisError)

    def test_accessibility_violation(self):
        """Test AccessibilityViolationError."""
        error = AccessibilityViolationError(
            "Missing content description",
            details={"element_id": "btn_submit", "wcag": "1.1.1"}
        )
        assert isinstance(error, AnalysisError)


class TestMLExceptions:
    """Test ML-related exceptions."""

    def test_model_not_found(self):
        """Test ModelNotFoundError."""
        error = ModelNotFoundError(
            "Model file not found",
            details={"model_path": "/models/selector_model.pkl"}
        )
        assert isinstance(error, MLError)

    def test_model_not_trained(self):
        """Test ModelNotTrainedError."""
        error = ModelNotTrainedError(
            "Model requires training",
            details={"model_name": "element_classifier"}
        )
        assert isinstance(error, MLError)

    def test_prediction_error(self):
        """Test PredictionError."""
        error = PredictionError(
            "Invalid input shape",
            details={"expected": (1, 128), "got": (1, 64)}
        )
        assert isinstance(error, MLError)

    def test_training_error(self):
        """Test TrainingError."""
        error = TrainingError(
            "Insufficient training data",
            details={"samples": 10, "required": 100}
        )
        assert isinstance(error, MLError)


class TestConfigurationExceptions:
    """Test configuration-related exceptions."""

    def test_invalid_config(self):
        """Test InvalidConfigError."""
        error = InvalidConfigError(
            "Invalid JSON syntax",
            details={"config_file": "config.json"}
        )
        assert isinstance(error, ConfigurationError)

    def test_missing_config(self):
        """Test MissingConfigError."""
        error = MissingConfigError(
            "Required field missing",
            details={"field": "appium.server_url"}
        )
        assert isinstance(error, ConfigurationError)


class TestLicenseExceptions:
    """Test license-related exceptions."""

    def test_invalid_license(self):
        """Test InvalidLicenseError."""
        error = InvalidLicenseError(
            "License key format invalid",
            details={"key": "INVALID-KEY"}
        )
        assert isinstance(error, LicenseError)

    def test_license_expired(self):
        """Test LicenseExpiredError."""
        error = LicenseExpiredError(
            "License expired",
            details={"expiry_date": "2024-01-01"}
        )
        assert isinstance(error, LicenseError)

    def test_feature_not_licensed(self):
        """Test FeatureNotLicensedError."""
        error = FeatureNotLicensedError(
            "Feature requires Pro license",
            details={"feature": "ml_advanced", "license_type": "free"}
        )
        assert isinstance(error, LicenseError)


class TestUtilityFunctions:
    """Test utility functions."""

    def test_format_error_message_mobile_test_error(self):
        """Test formatting MobileTestError."""
        error = DeviceNotFoundError(
            "Device not found",
            code="DEVICE_001",
            details={"device_id": "emulator-5554"}
        )

        msg = format_error_message(error)
        assert "[DEVICE_001]" in msg
        assert "Device not found" in msg
        assert "emulator-5554" in msg

    def test_format_error_message_standard_exception(self):
        """Test formatting standard exception."""
        error = ValueError("Invalid value")
        msg = format_error_message(error)
        assert "Invalid value" in msg

    def test_format_error_message_with_context(self):
        """Test formatting with additional context."""
        error = TimeoutError("Operation timed out")
        context = {"operation": "find_element", "timeout": 30}

        msg = format_error_message(error, context=context)
        assert "Operation timed out" in msg
        assert "Context:" in msg
        assert "find_element" in msg

    def test_is_retriable_error_true(self):
        """Test retriable errors."""
        # These should be retriable
        assert is_retriable_error(DeviceConnectionError("")) is True
        assert is_retriable_error(NetworkError("")) is True
        assert is_retriable_error(TimeoutError("")) is True
        assert is_retriable_error(SessionError("")) is True
        assert is_retriable_error(ElementNotInteractableError("")) is True

    def test_is_retriable_error_false(self):
        """Test non-retriable errors."""
        # These should NOT be retriable
        assert is_retriable_error(InvalidConfigError("")) is False
        assert is_retriable_error(LicenseExpiredError("")) is False
        assert is_retriable_error(ASTParsingError("")) is False
        assert is_retriable_error(ValueError("")) is False


class TestExceptionInheritance:
    """Test exception inheritance hierarchy."""

    def test_inheritance_chain(self):
        """Test that inheritance chain is correct."""
        error = ElementNotFoundError("Test")

        # Check full inheritance chain
        assert isinstance(error, ElementNotFoundError)
        assert isinstance(error, ElementError)
        assert isinstance(error, MobileTestError)
        assert isinstance(error, Exception)

    def test_catch_by_base_class(self):
        """Test catching exceptions by base class."""

        def raise_device_error():
            raise DeviceOfflineError("Device offline")

        # Can catch by base DeviceError
        with pytest.raises(DeviceError):
            raise_device_error()

        # Can catch by MobileTestError
        with pytest.raises(MobileTestError):
            raise_device_error()

    def test_catch_specific_exception(self):
        """Test catching specific exception type."""

        def raise_specific_error():
            raise ModelNotFoundError("Model missing")

        # Can catch specific type
        with pytest.raises(ModelNotFoundError):
            raise_specific_error()

        # Won't match wrong type
        with pytest.raises(ModelNotFoundError):
            # This should NOT catch ModelNotFoundError
            with pytest.raises(ModelNotTrainedError):
                raise_specific_error()


# ============================================================================
# Negative Tests
# ============================================================================

class TestNegativeCases:
    """Test negative and edge cases."""

    def test_empty_message(self):
        """Test exception with empty message."""
        error = MobileTestError("")
        assert error.message == ""

    def test_none_details(self):
        """Test exception with None details."""
        error = MobileTestError("Test", details=None)
        assert error.details == {}

    def test_to_dict_serializable(self):
        """Test that to_dict produces JSON-serializable output."""
        import json

        error = DeviceError(
            "Test error",
            code="TEST",
            details={"key": "value", "count": 42}
        )

        # Should be JSON serializable
        result = error.to_dict()
        json_str = json.dumps(result)
        assert json_str is not None

    def test_format_error_with_complex_context(self):
        """Test format_error with complex nested context."""
        error = APIError("Request failed")
        context = {
            "url": "https://api.example.com",
            "headers": {"Authorization": "Bearer token"},
            "retry_count": 3
        }

        msg = format_error_message(error, context=context)
        assert "Request failed" in msg
        assert "Context:" in msg


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
