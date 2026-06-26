"""
Comprehensive error handling utilities.
"""

import functools
import traceback
from typing import Callable, Any, Type, Tuple

import click

from framework.cli.rich_output import print_error, print_warning
from .logger import get_logger

logger = get_logger(__name__)


class RecorderError(Exception):
    """Base exception for Mobile Test Recorder errors."""
    pass


class ValidationError(RecorderError):
    """Raised when validation fails."""
    pass


class AnalysisError(RecorderError):
    """Raised when analysis fails."""
    pass


class GenerationError(RecorderError):
    """Raised when code generation fails."""
    pass


class IntegrationError(RecorderError):
    """Raised when project integration fails."""
    pass


def handle_cli_errors(
        exit_on_error: bool = True,
        show_traceback: bool = False,
) -> Callable:
    """
    Decorator for CLI commands to handle errors gracefully.

    Args:
        exit_on_error: Exit the program on error
        show_traceback: Show full traceback on error

    Example:
        @click.command()
        @handle_cli_errors(exit_on_error=True)
        def my_command():
            # Command logic
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)

            except click.Abort:
                # Let Click handle its own aborts
                raise

            except ValidationError as e:
                print_error(f"Validation error: {e}")
                logger.error(f"Validation failed in {func.__name__}: {e}")
                if show_traceback:
                    traceback.print_exc()
                if exit_on_error:
                    raise click.Abort()

            except (AnalysisError, GenerationError, IntegrationError) as e:
                print_error(f"Operation failed: {e}")
                logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                if show_traceback:
                    traceback.print_exc()
                if exit_on_error:
                    raise click.Abort()

            except FileNotFoundError as e:
                print_error(f"File not found: {e.filename}")
                logger.error(f"File not found in {func.__name__}: {e}")
                if exit_on_error:
                    raise click.Abort()

            except PermissionError as e:
                print_error(f"Permission denied: {e}")
                logger.error(f"Permission error in {func.__name__}: {e}")
                if exit_on_error:
                    raise click.Abort()

            except KeyboardInterrupt:
                print_warning("\nOperation cancelled by user")
                logger.info(f"User cancelled {func.__name__}")
                if exit_on_error:
                    raise click.Abort()

            except Exception as e:
                print_error(f"Unexpected error: {e}")
                logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                if show_traceback:
                    traceback.print_exc()
                if exit_on_error:
                    raise click.Abort()

        return wrapper

    return decorator


def safe_file_operation(
        operation: Callable,
        *args: Any,
        error_message: str = "File operation failed",
        default: Any = None,
        **kwargs: Any,
) -> Tuple[bool, Any]:
    """
    Safely execute a file operation with error handling.

    Args:
        operation: Function to execute
        *args: Arguments for the function
        error_message: Error message to log
        default: Default value to return on error
        **kwargs: Keyword arguments for the function

    Returns:
        Tuple of (success: bool, result: Any)

    Example:
        success, data = safe_file_operation(
            json.load,
            file_handle,
            error_message="Failed to load JSON"
        )
    """
    try:
        result = operation(*args, **kwargs)
        return True, result
    except FileNotFoundError as e:
        logger.error(f"{error_message}: File not found - {e}")
        return False, default
    except PermissionError as e:
        logger.error(f"{error_message}: Permission denied - {e}")
        return False, default
    except Exception as e:
        logger.error(f"{error_message}: {e}", exc_info=True)
        return False, default


def validate_and_raise(
        condition: bool,
        message: str,
        error_class: Type[RecorderError] = ValidationError,
) -> None:
    """
    Validate a condition and raise an error if it fails.

    Args:
        condition: Condition to check
        message: Error message
        error_class: Exception class to raise

    Raises:
        error_class: If condition is False

    Example:
        validate_and_raise(
            project_path.exists(),
            f"Project path does not exist: {project_path}"
        )
    """
    if not condition:
        raise error_class(message)
