"""
File operation utilities.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .logger import get_logger
from .validator import validate_path, ValidationError

logger = get_logger(__name__)


def safe_read_file(file_path: Path, encoding: str = "utf-8") -> Optional[str]:
    """
    Safely read a text file with error handling.

    Args:
        file_path: Path to the file
        encoding: File encoding

    Returns:
        File contents or None if error occurs
    """
    try:
        validated_path = validate_path(file_path, must_exist=True, must_be_file=True)
        return validated_path.read_text(encoding=encoding)
    except (ValidationError, IOError, OSError) as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        return None


def safe_write_file(
        file_path: Path,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True,
) -> bool:
    """
    Safely write content to a file with error handling.

    Args:
        file_path: Path to the file
        content: Content to write
        encoding: File encoding
        create_dirs: Create parent directories if they don't exist

    Returns:
        True if successful, False otherwise
    """
    try:
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(content, encoding=encoding)
        logger.debug(f"Successfully wrote file: {file_path}")
        return True
    except (IOError, OSError) as e:
        logger.error(f"Failed to write file {file_path}: {e}")
        return False


def load_json(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Load JSON file with error handling.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data or None if error occurs
    """
    try:
        validated_path = validate_path(file_path, must_exist=True, must_be_file=True)
        with validated_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (ValidationError, json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load JSON from {file_path}: {e}")
        return None


def save_json(
        file_path: Path,
        data: Dict[str, Any],
        indent: int = 2,
        create_dirs: bool = True,
) -> bool:
    """
    Save data to JSON file with error handling.

    Args:
        file_path: Path to JSON file
        data: Data to save
        indent: JSON indentation level
        create_dirs: Create parent directories if they don't exist

    Returns:
        True if successful, False otherwise
    """
    try:
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)

        logger.debug(f"Successfully saved JSON to: {file_path}")
        return True
    except (IOError, TypeError) as e:
        logger.error(f"Failed to save JSON to {file_path}: {e}")
        return False


def load_yaml(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Load YAML file with error handling.

    Args:
        file_path: Path to YAML file

    Returns:
        Parsed YAML data or None if error occurs
    """
    try:
        validated_path = validate_path(file_path, must_exist=True, must_be_file=True)
        with validated_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (ValidationError, yaml.YAMLError, IOError) as e:
        logger.error(f"Failed to load YAML from {file_path}: {e}")
        return None


def save_yaml(
        file_path: Path,
        data: Dict[str, Any],
        create_dirs: bool = True,
) -> bool:
    """
    Save data to YAML file with error handling.

    Args:
        file_path: Path to YAML file
        data: Data to save
        create_dirs: Create parent directories if they don't exist

    Returns:
        True if successful, False otherwise
    """
    try:
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        with file_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)

        logger.debug(f"Successfully saved YAML to: {file_path}")
        return True
    except (IOError, yaml.YAMLError) as e:
        logger.error(f"Failed to save YAML to {file_path}: {e}")
        return False


def ensure_directory(dir_path: Path) -> bool:
    """
    Ensure directory exists, create if necessary.

    Args:
        dir_path: Path to directory

    Returns:
        True if directory exists or was created successfully
    """
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        logger.error(f"Failed to create directory {dir_path}: {e}")
        return False
