"""
App Model - Core data structures for representing mobile application behavior

This module defines the semantic model of a mobile application including:
- Screens and UI elements
- Actions and transitions
- API calls and correlations
- State machine
- Navigation flows
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .api import APICall
from .element import Element, Action
# Import all model components
from .enums import Platform, ActionType, ElementType, TestPriority, SelectorStability
from .flow import Flow, StateMachine, StateTransition
from .screen import Screen, Precondition
from .selector import Selector

# Re-export all models for backward compatibility
__all__ = [
    # Enums
    "Platform",
    "ActionType",
    "ElementType",
    "TestPriority",
    "SelectorStability",
    # Core models
    "Selector",
    "Element",
    "Action",
    "APICall",
    "Precondition",
    "Screen",
    "StateTransition",
    "StateMachine",
    "Flow",
    "AppModelMeta",
    "AppModel",
]


class AppModelMeta(BaseModel):
    """
    Metadata about the app model
    """
    schema_version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    app_version: str
    platform: Platform
    recorded_at: datetime = Field(default_factory=datetime.now)
    session_id: Optional[str] = None


class AppModel(BaseModel):
    """
    Complete application model

    This is the central data structure that represents everything
    we know about the mobile application's behavior
    """
    meta: AppModelMeta
    screens: Dict[str, Screen] = Field(default_factory=dict)
    api_calls: Dict[str, APICall] = Field(default_factory=dict)
    state_machine: Optional[StateMachine] = None
    flows: List[Flow] = Field(default_factory=list)

    def validate_consistency(self) -> List[str]:
        """
        Validate model consistency

        Returns list of validation errors
        """
        errors = []

        # Check that all referenced screens exist
        for screen_name, screen in self.screens.items():
            for action in screen.actions:
                for target_screen in action.transitions.values():
                    if target_screen not in self.screens:
                        errors.append(
                            f"Screen '{screen_name}': "
                            f"references non-existent screen '{target_screen}'"
                        )

                # Check that referenced API calls exist
                if action.api_call and action.api_call not in self.api_calls:
                    errors.append(
                        f"Screen '{screen_name}': "
                        f"references non-existent API '{action.api_call}'"
                    )

        return errors

    def get_screen(self, name: str) -> Optional[Screen]:
        """Get screen by name"""
        return self.screens.get(name)

    def get_api_call(self, name: str) -> Optional[APICall]:
        """Get API call by name"""
        return self.api_calls.get(name)

    model_config = {
        "json_schema_extra": {
            "example": {
                "meta": {
                    "schema_version": "1.0.0",
                    "app_version": "1.2.3",
                    "platform": "android",
                    "recorded_at": "2025-12-19T10:00:00Z"
                },
                "screens": {
                    "LoginScreen": {
                        "name": "LoginScreen",
                        "elements": [],
                        "actions": []
                    }
                },
                "api_calls": {},
                "flows": []
            }
        }
    }
