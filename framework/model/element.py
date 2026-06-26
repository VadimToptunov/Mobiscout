"""
UI Element and Action models.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .enums import ElementType, ActionType, TestPriority
from .selector import Selector


class Element(BaseModel):
    """
    UI Element representation

    Represents a single interactive or visible element on screen
    """
    id: str = Field(..., description="Unique element identifier")
    type: ElementType = Field(..., description="Element type")
    selector: Selector = Field(..., description="Element selector")
    text: Optional[str] = Field(None, description="Visible text content")
    capabilities: List[str] = Field(
        default_factory=list,
        description="Element capabilities (tappable, input, scrollable, etc.)"
    )
    test_priority: TestPriority = TestPriority.MEDIUM
    visible_when: Optional[List[str]] = Field(
        None,
        description="Conditions when element is visible"
    )
    description: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "login_button",
                "type": "button",
                "selector": {
                    "android": "id:login_btn",
                    "ios": "accessibility:login_btn"
                },
                "capabilities": ["tappable"],
                "test_priority": "high"
            }
        }
    }


class Action(BaseModel):
    """
    User action on an element

    Represents a recorded or possible action that triggers state changes
    """
    name: str = Field(..., description="Action name")
    ui_action: ActionType = Field(..., description="Type of UI interaction")
    element_id: str = Field(..., description="Target element ID")
    api_call: Optional[str] = Field(None, description="Triggered API call")
    transitions: Dict[str, str] = Field(
        default_factory=dict,
        description="State transitions (success/failure/cancel)"
    )
    validation: Optional[str] = Field(
        None,
        description="Validation rule for this action"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "perform_login",
                "ui_action": "tap",
                "element_id": "login_button",
                "api_call": "auth_login",
                "transitions": {
                    "success": "HomeScreen",
                    "failure": "LoginErrorScreen"
                }
            }
        }
    }
