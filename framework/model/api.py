"""
API Call model for network endpoint representation.
STEP 7: Paid Modules Enhancement - API Model Refactoring
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class APICall(BaseModel):
    """
    API endpoint representation

    Captured from network observations or static analysis.
    Renamed 'schema' to 'request_schema' to avoid shadowing BaseModel attribute.
    """
    name: str = Field(..., description="API call identifier")
    endpoint: str = Field(..., description="API endpoint path")
    method: str = Field(..., description="HTTP method (GET, POST, PUT, DELETE, PATCH)")
    request_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="Request/Response schema definition"
    )
    responses: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Observed responses from API calls"
    )
    triggers_state_change: Optional[str] = Field(
        None,
        description="State machine event this API triggers"
    )

    # Pydantic v2 configuration
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "auth_login",
                "endpoint": "/api/v1/auth/login",
                "method": "POST",
                "request_schema": {
                    "username": "string",
                    "password": "string"
                },
                "triggers_state_change": "login_success"
            }
        },
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True
    )
