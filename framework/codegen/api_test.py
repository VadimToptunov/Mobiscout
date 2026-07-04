"""
API test generation via the codegen pipeline.

Builds runnable pytest + requests contract tests from the AppModel's api_calls:
one test per endpoint that issues the request and asserts the endpoint exists
and the server did not error (status < 500). This is the API facet of
comprehensive testing, complementing the UI crawl.

    AppModel.api_calls --> emit_api_tests --> test_api.py
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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

    @property
    def has_body(self) -> bool:
        return self.method in _BODY_METHODS and bool(self.body)


def _build(app_model) -> List[_ApiTest]:
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
        tests.append(_ApiTest(name=name, method=method, endpoint=endpoint, body=body))
    return tests


def emit_api_tests(app_model, base_url: str = "http://localhost:8000") -> Dict[str, str]:
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
