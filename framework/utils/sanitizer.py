"""
Code identifier sanitization utilities.
"""

import re


def sanitize_identifier(name: str, default: str = "item") -> str:
    """
    Convert a string into a valid Python identifier.

    Args:
        name: Input string to sanitize
        default: Default name if input is invalid

    Returns:
        Valid Python identifier

    Examples:
        >>> sanitize_identifier("My Screen")
        'my_screen'
        >>> sanitize_identifier("123-invalid")
        'invalid_123'
        >>> sanitize_identifier("Button!")
        'button'
    """
    if not name:
        return default

    # Convert to lowercase and replace spaces/hyphens with underscores
    sanitized = name.lower().replace(" ", "_").replace("-", "_")

    # Remove invalid characters
    sanitized = re.sub(r"[^a-z0-9_]", "", sanitized)

    # Remove leading digits
    sanitized = re.sub(r"^[0-9]+", "", sanitized)

    # Ensure not empty
    if not sanitized:
        return default

    # Ensure doesn't conflict with Python keywords
    python_keywords = {
        "and",
        "as",
        "assert",
        "break",
        "class",
        "continue",
        "de",
        "del",
        "eli",
        "else",
        "except",
        "False",
        "finally",
        "for",
        "from",
        "global",
        "i",
        "import",
        "in",
        "is",
        "lambda",
        "None",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "True",
        "try",
        "while",
        "with",
        "yield",
    }

    if sanitized in python_keywords:
        sanitized = f"{sanitized}_"

    return sanitized


def sanitize_class_name(name: str, default: str = "Item") -> str:
    """
    Convert a string into a valid Python class name (PascalCase).

    Args:
        name: Input string to sanitize
        default: Default name if input is invalid

    Returns:
        Valid Python class name in PascalCase

    Examples:
        >>> sanitize_class_name("home screen")
        'HomeScreen'
        >>> sanitize_class_name("api-client")
        'ApiClient'
        >>> sanitize_class_name("123Test")
        'Test123'
    """
    if not name:
        return default

    # Split by spaces, hyphens, and underscores
    parts = re.split(r"[\s\-_]+", name)

    # Capitalize each part and remove invalid characters
    cleaned_parts = []
    for part in parts:
        # Remove non-alphanumeric characters
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", part)
        if cleaned:
            # Capitalize first letter
            cleaned_parts.append(cleaned[0].upper() + cleaned[1:].lower())

    if not cleaned_parts:
        return default

    result = "".join(cleaned_parts)

    # Remove leading digits
    result = re.sub(r"^[0-9]+", "", result)

    if not result:
        return default

    return result


def sanitize_filename(name: str, default: str = "file") -> str:
    """
    Convert a string into a valid filename.

    Args:
        name: Input string to sanitize
        default: Default name if input is invalid

    Returns:
        Valid filename (without extension)

    Examples:
        >>> sanitize_filename("My File.txt")
        'my_file'
        >>> sanitize_filename("Test/File")
        'test_file'
    """
    if not name:
        return default

    # Remove extension if present
    name = name.rsplit(".", 1)[0] if "." in name else name

    # Convert to lowercase
    sanitized = name.lower()

    # Replace spaces and invalid characters with underscores
    sanitized = re.sub(r"[^\w\-]", "_", sanitized)

    # Remove multiple consecutive underscores
    sanitized = re.sub(r"_+", "_", sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    if not sanitized:
        return default

    return sanitized
