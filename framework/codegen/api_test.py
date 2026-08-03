"""
API test generation via the codegen pipeline.

Builds runnable pytest + requests contract tests from the AppModel's api_calls:
one test per endpoint that issues the request and asserts the endpoint exists
and the server did not error (status < 500). This is the API facet of
comprehensive testing, complementing the UI crawl.

    AppModel.api_calls --> emit_api_tests --> test_api.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.model.app_model import AppModel

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from framework.codegen.emitters._naming import snake

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "api_test")
_BODY_METHODS = {"post", "put", "patch"}
_PATH_PARAM = re.compile(r"\{[^}]+\}")


@dataclass
class _ApiTest:
    name: str
    method: str  # lower-case: get/post/put/delete/patch
    endpoint: str  # path params substituted with a sample value
    body: Dict[str, str] = field(default_factory=dict)
    # Documented numeric status codes for the endpoint (e.g. from an OpenAPI spec).
    # When known, the test asserts the response is one of them — a real contract
    # check — instead of merely "not a 5xx". Empty => fall back to the 5xx check.
    expected_statuses: List[int] = field(default_factory=list)
    # Top-level keys the success response body should carry (from a 2xx response
    # schema). When known, the test also validates the response shape on 2xx.
    response_keys: List[str] = field(default_factory=list)

    @property
    def has_body(self) -> bool:
        return self.method in _BODY_METHODS and bool(self.body)


def _response_keys(responses: Any) -> List[str]:
    """Top-level field names of the first 2xx response that carries a schema
    (``{"status": "200", "schema": {field: type, ...}}``), sorted. Empty if none."""
    for response in responses or []:
        status = str((response or {}).get("status", "")).strip()
        schema = (response or {}).get("schema")
        if status.startswith("2") and isinstance(schema, dict) and schema:
            return sorted(schema.keys())
    return []


def _expected_statuses(responses: Any) -> List[int]:
    """The documented numeric status codes from an APICall's ``responses`` (OpenAPI
    keys like ``"200"``/``"404"``; non-numeric keys such as ``"default"`` or
    ``"2XX"`` are skipped). Sorted and de-duplicated."""
    codes = set()
    for response in responses or []:
        raw = str((response or {}).get("status", "")).strip()
        if raw.isdigit() and len(raw) == 3:
            codes.add(int(raw))
    return sorted(codes)


def _build(app_model: AppModel) -> List[_ApiTest]:
    tests: List[_ApiTest] = []
    used = set()
    for call in app_model.api_calls.values():
        method = (call.method or "GET").lower()
        # Substitute path params (/cards/{id}/block -> /cards/1/block).
        endpoint = _PATH_PARAM.sub("1", call.endpoint)
        name = snake(call.name) or f"{method}_{snake(endpoint)}"
        while name in used:
            name += "_x"
        used.add(name)
        body = {snake(k): "test" for k in (call.request_schema or {}).keys()} if method in _BODY_METHODS else {}
        tests.append(
            _ApiTest(
                name=name,
                method=method,
                endpoint=endpoint,
                body=body,
                expected_statuses=_expected_statuses(getattr(call, "responses", None)),
                response_keys=_response_keys(getattr(call, "responses", None)),
            )
        )
    return tests


def emit_api_tests(app_model: AppModel, base_url: str = "http://localhost:8000") -> Dict[str, str]:
    """Render a pytest+requests API contract test module (empty if no api_calls)."""
    tests = _build(app_model)
    if not tests:
        return {}
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    content = env.get_template("test_api.py.j2").render(tests=tests, base_url=base_url)
    return {"test_api.py": content}
