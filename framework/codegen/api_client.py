"""
API client generation via the codegen pipeline.

Builds a requests-based Python API client from the canonical AppModel's
api_calls. Supersedes generators/api_client_gen.py (whose template referenced a
non-existent ``api_call.parameters`` field; this reads the real
``request_schema``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from framework.codegen.emitters._naming import snake

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "api_client")
_BODY_METHODS = {"POST", "PUT", "PATCH"}


@dataclass
class _Endpoint:
    name: str
    method: str
    endpoint: str
    params: List[str] = field(default_factory=list)

    @property
    def body_kw(self) -> str:
        return "json" if self.method.upper() in _BODY_METHODS else "params"


def _build_endpoints(app_model) -> List[_Endpoint]:
    endpoints: List[_Endpoint] = []
    for call in app_model.api_calls.values():
        params = [snake(k) for k in (call.request_schema or {}).keys()]
        endpoints.append(
            _Endpoint(
                name=snake(call.name),
                method=(call.method or "GET").upper(),
                endpoint=call.endpoint,
                params=params,
            )
        )
    return endpoints


def emit_api_client(app_model) -> Dict[str, str]:
    """Render a single api_client.py from the model's api_calls (empty dict if none)."""
    endpoints = _build_endpoints(app_model)
    if not endpoints:
        return {}
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    content = env.get_template("api_client.py.j2").render(endpoints=endpoints)
    return {"api_client.py": content}
