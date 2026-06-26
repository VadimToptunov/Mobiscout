"""
Flow and State Machine models.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class StateTransition(BaseModel):
    """
    State machine transition
    """
    from_state: str
    to_state: str
    trigger: str
    condition: Optional[str] = None


class StateMachine(BaseModel):
    """
    Application state machine

    Models high-level application states and transitions
    """
    states: List[str] = Field(default_factory=list)
    transitions: List[StateTransition] = Field(default_factory=list)
    initial_state: Optional[str] = None


class Flow(BaseModel):
    """
    Navigation flow (sequence of screens and actions)
    """
    name: str
    description: Optional[str] = None
    steps: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Sequence of screen/action pairs"
    )
