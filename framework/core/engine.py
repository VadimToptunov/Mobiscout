"""
Core UI models: Language, UIElement, Screen.

Shared data types consumed by the codegen pipeline (framework/codegen). The
legacy CoreEngine multi-language generator that used to live here was removed —
codegen's IR + emitters supersede it, so only the plain data types remain.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class Language(Enum):
    """Supported programming languages"""

    PYTHON = "python"
    JAVA = "java"
    KOTLIN = "kotlin"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    CSHARP = "csharp"
    GO = "go"
    SWIFT = "swift"


@dataclass
class UIElement:
    """Discovered UI element."""

    id: str
    type: str
    label: Optional[str]
    xpath: Optional[str]
    accessibility_id: Optional[str]
    bounds: Dict[str, int]
    visible: bool
    enabled: bool


@dataclass
class Screen:
    """Discovered screen with elements and flow connections"""

    id: str
    name: str
    elements: List[UIElement]
    transitions: List[str]  # Screen IDs this can transition to
    api_calls: List[Dict[str, Any]]  # API calls made on this screen

    def find_interactive_elements(self) -> List[UIElement]:
        """Find elements that can be interacted with"""
        return [e for e in self.elements if e.enabled and e.type in ("button", "textfield", "switch")]
