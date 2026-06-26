"""
Mobile Automation Backend Interface

Abstract interface for different mobile automation backends:
- Appium (v1/v2)
- Espresso / UIAutomator (Android)
- XCTest / XCUITest (iOS)
- Detox (React Native)
- Maestro
- Playwright Mobile (future)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class BackendCapability:
    """Describes what a backend can do."""
    name: str
    supports_ios: bool
    supports_android: bool
    supports_web: bool
    supports_ui_tree: bool
    supports_screenshot: bool
    supports_tap: bool
    supports_swipe: bool
    supports_type: bool
    supports_gestures: bool
    requires_app_modification: bool  # e.g., Espresso needs test APK
    execution_speed: str  # "fast", "medium", "slow"


class MobileAutomationBackend(ABC):
    """Abstract base class for mobile automation backends."""

    @abstractmethod
    def get_capabilities(self) -> BackendCapability:
        """Return backend capabilities."""
        pass

    @abstractmethod
    def start_session(self, device_id: str, app_path: Optional[str] = None,
                      capabilities: Optional[Dict[str, Any]] = None) -> str:
        """
        Start automation session.
        
        Returns:
            session_id: Unique session identifier
        """
        pass

    @abstractmethod
    def stop_session(self, session_id: str) -> None:
        """Stop automation session."""
        pass

    @abstractmethod
    def get_screenshot(self, session_id: str) -> bytes:
        """
        Capture device screenshot.
        
        Returns:
            PNG image bytes
        """
        pass

    @abstractmethod
    def get_ui_tree(self, session_id: str) -> str:
        """
        Get UI element tree.
        
        Returns:
            XML or JSON string representing UI hierarchy
        """
        pass

    @abstractmethod
    def tap(self, session_id: str, x: int, y: int) -> None:
        """Tap at coordinates."""
        pass

    @abstractmethod
    def swipe(self, session_id: str, start_x: int, start_y: int,
              end_x: int, end_y: int, duration_ms: int = 300) -> None:
        """Swipe gesture."""
        pass

    @abstractmethod
    def type_text(self, session_id: str, text: str, element_id: Optional[str] = None) -> None:
        """Type text into element or active field."""
        pass

    @abstractmethod
    def find_element(self, session_id: str, strategy: str, value: str) -> Optional[str]:
        """
        Find element by selector.
        
        Args:
            strategy: "id", "xpath", "accessibility_id", "class_name", etc.
            value: Selector value
            
        Returns:
            element_id or None
        """
        pass

    @abstractmethod
    def get_element_bounds(self, session_id: str, element_id: str) -> Dict[str, int]:
        """
        Get element bounds.
        
        Returns:
            {"x": int, "y": int, "width": int, "height": int}
        """
        pass


class BackendFactory:
    """Factory for creating backend instances."""

    _backends: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, backend_class: type) -> None:
        """Register a backend implementation."""
        cls._backends[name] = backend_class

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> MobileAutomationBackend:
        """Create backend instance by name."""
        if name not in cls._backends:
            raise ValueError(f"Unknown backend: {name}. Available: {list(cls._backends.keys())}")
        return cls._backends[name](**kwargs)

    @classmethod
    def list_backends(cls) -> List[str]:
        """List available backend names."""
        return list(cls._backends.keys())
