"""
Enum types for the mobile application model.
"""

from enum import Enum


class Platform(str, Enum):
    """Supported platforms"""
    ANDROID = "android"
    IOS = "ios"
    CROSS_PLATFORM = "cross-platform"


class ActionType(str, Enum):
    """Types of UI actions"""
    TAP = "tap"
    SWIPE = "swipe"
    INPUT = "input"
    LONG_PRESS = "long_press"
    DOUBLE_TAP = "double_tap"


class ElementType(str, Enum):
    """Types of UI elements"""
    BUTTON = "button"
    INPUT = "input"
    TEXT = "text"
    LIST = "list"
    IMAGE = "image"
    CHECKBOX = "checkbox"
    SWITCH = "switch"
    RADIO = "radio"
    WEBVIEW = "webview"
    GENERIC = "generic"


class TestPriority(str, Enum):
    """Element testing priority"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    IGNORE = "ignore"


class SelectorStability(str, Enum):
    """Selector stability assessment"""
    HIGH = "high"  # accessibility ID, resource ID
    MEDIUM = "medium"  # text-based
    LOW = "low"  # XPath with index
    UNKNOWN = "unknown"
