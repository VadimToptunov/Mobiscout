"""
Screen model with UI elements and actions.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from .element import Element, Action


class Precondition(BaseModel):
    """
    Condition that must be satisfied to reach a screen
    """
    state: Optional[str] = None
    feature_flag: Optional[str] = None
    api_condition: Optional[str] = None


class Screen(BaseModel):
    """
    Screen (Activity/ViewController) representation

    Represents a logical UI state with elements and possible actions
    """
    name: str = Field(..., description="Screen identifier")
    class_name: Optional[str] = Field(
        None,
        description="Activity/ViewController class name"
    )
    preconditions: List[Precondition] = Field(
        default_factory=list,
        description="Conditions to reach this screen"
    )
    elements: List[Element] = Field(
        default_factory=list,
        description="UI elements on this screen"
    )
    actions: List[Action] = Field(
        default_factory=list,
        description="Possible actions on this screen"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "LoginScreen",
                "class_name": "com.app.ui.LoginActivity",
                "elements": [
                    {
                        "id": "username_field",
                        "type": "input",
                        "selector": {"android": "id:username"}
                    }
                ],
                "actions": [
                    {
                        "name": "login",
                        "ui_action": "tap",
                        "element_id": "login_button"
                    }
                ]
            }
        }
    }
