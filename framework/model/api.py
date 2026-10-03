"""
API Call model for network endpoint representation.
STEP 7: Paid Modules Enhancement - API Model Refactoring
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ConfigDict


def endpoint_path(endpoint: str) -> str:
    """An endpoint as a path: an absolute URL (iOS URLSession, captured traffic) is reduced
    to its path so a generated test can prepend its BASE_URL; a path passes through."""
    if endpoint.startswith(("http://", "https://")):
        return urlparse(endpoint).path or "/"
    return endpoint


def call_name(method: str, endpoint: str) -> str:
    """A readable identifier for an API call: ``get_users`` for GET /users."""
    path = endpoint_path(endpoint)
    slug = "".join(char if char.isalnum() else "_" for char in path).strip("_")
    return f"{method.lower()}_{(slug or 'root').lower()[:40]}"


class APICall(BaseModel):
    """
    An API endpoint the app calls — THE one representation across discovery (source
    analyzers, captured traffic, OpenAPI) and generation.

    One captured request is a different thing (an observation with a timestamp, headers and
    body): that is ``api_analyzer.CapturedCall``, and many of them group into one APICall.
    Renamed 'schema' to 'request_schema' to avoid shadowing BaseModel attribute.
    """

    name: str = Field(..., description="API call identifier")
    endpoint: str = Field(..., description="API endpoint path")
    method: str = Field(..., description="HTTP method (GET, POST, PUT, DELETE, PATCH)")
    request_schema: Dict[str, Any] = Field(default_factory=dict, description="Request/Response schema definition")
    responses: List[Dict[str, Any]] = Field(default_factory=list, description="Observed responses from API calls")
    triggers_state_change: Optional[str] = Field(default=None, description="State machine event this API triggers")
    # What a static analyzer could tell about the endpoint, when it could.
    authentication: Optional[str] = Field(default=None, description="Auth scheme the call needs (e.g. Bearer Token)")
    rate_limit: Optional[str] = Field(default=None, description="Rate limit, when documented")
    description: Optional[str] = Field(default=None, description="What the endpoint is, in words")
    source_file: Optional[str] = Field(default=None, description="Where in the app's source it was found")

    @property
    def response_schema(self) -> Dict[str, Any]:
        """The schema of the first successful (2xx) response, or ``{}``."""
        for response in self.responses:
            if _is_success(response):
                return dict(response.get("schema") or {})
        return {}

    @property
    def error_responses(self) -> List[Dict[str, Any]]:
        """Every response that is not a success (an error status, a network error)."""
        return [response for response in self.responses if not _is_success(response)]

    # Pydantic v2 configuration
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "auth_login",
                "endpoint": "/api/v1/auth/login",
                "method": "POST",
                "request_schema": {"username": "string", "password": "string"},
                "triggers_state_change": "login_success",
            }
        },
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True,
    )


def _is_success(response: Dict[str, Any]) -> bool:
    status = response.get("status")
    return isinstance(status, int) and 200 <= status < 300
