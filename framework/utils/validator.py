"""
Input validation utilities.
"""

from pathlib import Path
from typing import List, Optional, Tuple

from .logger import get_logger

logger = get_logger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_path(
        path: Path,
        must_exist: bool = True,
        must_be_dir: bool = False,
        must_be_file: bool = False,
        create_if_missing: bool = False,
) -> Path:
    """
    Validate a filesystem path.

    Args:
        path: Path to validate
        must_exist: Path must exist
        must_be_dir: Path must be a directory
        must_be_file: Path must be a file
        create_if_missing: Create directory if it doesn't exist

    Returns:
        Validated Path object

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(path, Path):
        path = Path(path)

    # Check existence
    if must_exist and not path.exists():
        if create_if_missing and must_be_dir:
            logger.info(f"Creating directory: {path}")
            path.mkdir(parents=True, exist_ok=True)
        else:
            raise ValidationError(f"Path does not exist: {path}")

    # Check if directory
    if must_be_dir and path.exists() and not path.is_dir():
        raise ValidationError(f"Path is not a directory: {path}")

    # Check if file
    if must_be_file and path.exists() and not path.is_file():
        raise ValidationError(f"Path is not a file: {path}")

    return path.resolve()


def validate_project_structure(
        project_path: Path,
        required_files: Optional[List[str]] = None,
        required_dirs: Optional[List[str]] = None,
) -> Tuple[bool, List[str]]:
    """
    Validate that a project has the expected structure.

    Args:
        project_path: Root path of the project
        required_files: List of required file paths (relative to project_path)
        required_dirs: List of required directory paths (relative to project_path)

    Returns:
        Tuple of (is_valid, missing_items)

    Examples:
        >>> validate_project_structure(
        ...     Path("/path/to/project"),
        ...     required_files=["setup.py", "README.md"],
        ...     required_dirs=["src", "tests"]
        ... )
        (True, [])
    """
    missing = []

    # Validate project path exists
    try:
        project_path = validate_path(project_path, must_exist=True, must_be_dir=True)
    except ValidationError as e:
        return False, [str(e)]

    # Check required files
    if required_files:
        for file_path in required_files:
            full_path = project_path / file_path
            if not full_path.is_file():
                missing.append(f"Missing file: {file_path}")

    # Check required directories
    if required_dirs:
        for dir_path in required_dirs:
            full_path = project_path / dir_path
            if not full_path.is_dir():
                missing.append(f"Missing directory: {dir_path}")

    return len(missing) == 0, missing


def validate_android_project(project_path: Path) -> Tuple[bool, List[str]]:
    """
    Validate Android project structure.

    Args:
        project_path: Root path of the Android project

    Returns:
        Tuple of (is_valid, missing_items)
    """
    required_files = ["build.gradle", "settings.gradle"]
    required_dirs = ["app/src"]

    # Check for Kotlin DSL variants
    if not (project_path / "build.gradle").exists():
        if (project_path / "build.gradle.kts").exists():
            required_files = ["build.gradle.kts", "settings.gradle.kts"]

    return validate_project_structure(
        project_path,
        required_files=required_files,
        required_dirs=required_dirs,
    )


def validate_ios_project(project_path: Path) -> Tuple[bool, List[str]]:
    """
    Validate iOS project structure.

    Args:
        project_path: Root path of the iOS project

    Returns:
        Tuple of (is_valid, missing_items)
    """
    # Look for .xcodeproj or .xcworkspace
    has_xcode_project = any(
        path.suffix in [".xcodeproj", ".xcworkspace"]
        for path in project_path.glob("*")
    )

    if not has_xcode_project:
        return False, ["Missing .xcodeproj or .xcworkspace"]

    return True, []


def validate_output_format(format_str: str, allowed_formats: List[str]) -> str:
    """
    Validate output format string.

    Args:
        format_str: Format string to validate
        allowed_formats: List of allowed format strings

    Returns:
        Validated format string (lowercase)

    Raises:
        ValidationError: If format is not allowed
    """
    format_lower = format_str.lower()
    if format_lower not in [f.lower() for f in allowed_formats]:
        raise ValidationError(
            f"Invalid format '{format_str}'. Allowed: {', '.join(allowed_formats)}"
        )
    return format_lower
