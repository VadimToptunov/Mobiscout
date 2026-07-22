"""Coverage for the CLI error-handling utilities: the handle_cli_errors
decorator (one branch per exception kind), safe_file_operation, and
validate_and_raise. Previously 25% covered."""

import click
import pytest

from framework.utils.error_handling import (
    AnalysisError,
    GenerationError,
    IntegrationError,
    ValidationError,
    handle_cli_errors,
    safe_file_operation,
    validate_and_raise,
)

# --- handle_cli_errors ------------------------------------------------------


def test_passes_through_return_value_on_success():
    @handle_cli_errors()
    def ok():
        return 42

    assert ok() == 42


def test_click_abort_is_reraised_untouched():
    @handle_cli_errors()
    def aborts():
        raise click.Abort()

    with pytest.raises(click.Abort):
        aborts()


@pytest.mark.parametrize(
    "exc",
    [
        ValidationError("bad"),
        AnalysisError("bad"),
        GenerationError("bad"),
        IntegrationError("bad"),
        PermissionError("denied"),
        KeyboardInterrupt(),
        RuntimeError("unexpected"),
    ],
)
def test_known_errors_become_click_abort_when_exit_on_error(exc):
    @handle_cli_errors(exit_on_error=True)
    def boom():
        raise exc

    with pytest.raises(click.Abort):
        boom()


def test_file_not_found_becomes_abort():
    @handle_cli_errors(exit_on_error=True)
    def missing():
        raise FileNotFoundError(2, "No such file", "gone.txt")

    with pytest.raises(click.Abort):
        missing()


def test_no_abort_when_exit_on_error_false():
    @handle_cli_errors(exit_on_error=False)
    def boom():
        raise ValidationError("bad")

    assert boom() is None  # swallowed, no abort


def test_show_traceback_path_still_aborts():
    @handle_cli_errors(exit_on_error=True, show_traceback=True)
    def boom():
        raise RuntimeError("with traceback")

    with pytest.raises(click.Abort):
        boom()


# --- safe_file_operation ----------------------------------------------------


def test_safe_file_operation_success():
    ok, result = safe_file_operation(lambda a, b: a + b, 2, 3)
    assert ok is True and result == 5


@pytest.mark.parametrize(
    "exc",
    [FileNotFoundError("x"), PermissionError("x"), ValueError("x")],
)
def test_safe_file_operation_failures_return_default(exc):
    def boom():
        raise exc

    ok, result = safe_file_operation(boom, default="fallback")
    assert ok is False and result == "fallback"


# --- validate_and_raise -----------------------------------------------------


def test_validate_and_raise_passes_when_true():
    validate_and_raise(True, "should not raise")  # no exception


def test_validate_and_raise_raises_default_validation_error():
    with pytest.raises(ValidationError):
        validate_and_raise(False, "nope")


def test_validate_and_raise_custom_error_class():
    with pytest.raises(GenerationError):
        validate_and_raise(False, "nope", error_class=GenerationError)
