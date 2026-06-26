"""
Selector model for cross-platform element location.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from .enums import SelectorStability


class Selector(BaseModel):
    """
    Cross-platform element selector with fallback strategies

    Supports multiple locator strategies:
    - android: Android-specific locator
    - ios: iOS-specific locator
    - test_id: Universal test identifier
    - xpath: XPath locator (fragile)
    """

    android: Optional[str] = None
    ios: Optional[str] = None
    test_id: Optional[str] = None
    xpath: Optional[str] = None
    android_fallback: List[str] = Field(default_factory=list)
    ios_fallback: List[str] = Field(default_factory=list)
    stability: SelectorStability = SelectorStability.UNKNOWN

    @field_validator("android", "ios", "test_id", "xpath")
    @classmethod
    def validate_locators(cls, v: Optional[str]) -> Optional[str]:
        """At least one locator must be provided"""
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "android": "id:com.app:id/login_button",
                "ios": "accessibility:login_button",
                "test_id": "login_button",
                "stability": "high",
            }
        }
    }
