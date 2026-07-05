"""OpenAPI/Swagger ingestion + review: spec -> APICalls (for tests) + findings."""

import json
from unittest.mock import patch

from framework.codegen.api_test import emit_api_tests
from framework.codegen.openapi import load_spec, parse_openapi, review_markdown, review_openapi

SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Shop API", "version": "1.0"},
    "components": {
        "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
        "schemas": {
            "NewOrder": {
                "type": "object",
                "properties": {"item_id": {"type": "integer"}, "qty": {"type": "integer"}},
            }
        },
    },
    "paths": {
        "/orders": {
            "post": {
                "operationId": "createOrder",
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/NewOrder"}}}},
                "responses": {"201": {"description": "created"}},
            }
        },
        "/orders/{id}": {
            "get": {  # no operationId, no 2xx, undeclared path param -> findings
                "responses": {"500": {"description": "err"}},
            }
        },
    },
}


def test_parse_extracts_endpoints_and_body_schema():
    calls = {c.name: c for c in parse_openapi(SPEC)}
    assert "createOrder" in calls
    order = calls["createOrder"]
    assert order.method == "POST" and order.endpoint == "/orders"
    # $ref request body was resolved to its fields
    assert set(order.request_schema) == {"item_id", "qty"}
    # the GET got a synthesised name from method+path
    assert any(c.endpoint == "/orders/{id}" and c.method == "GET" for c in calls.values())


def test_parsed_spec_feeds_api_test_generation():
    from types import SimpleNamespace

    calls = parse_openapi(SPEC)
    model = SimpleNamespace(api_calls={c.name: c for c in calls})
    files = emit_api_tests(model, base_url="https://api.shop.test")
    body = files["test_api.py"]
    assert "def test_create_order" in body
    assert "/orders" in body


def test_review_flags_spec_gaps():
    findings = review_openapi(SPEC)
    issues = {(f.endpoint, f.issue) for f in findings}
    assert ("GET /orders/{id}", "No operationId") in issues
    assert any("path parameter" in i.lower() or "not declared" in i.lower() for _, i in issues)
    assert any(f.issue.startswith("No 2xx") for f in findings)
    # markdown renders inventory + review sections
    md = review_markdown(SPEC, parse_openapi(SPEC), findings)
    assert "## Endpoints" in md and "## Review" in md and "createOrder" in md


def test_load_spec_local_json_auto_detected(tmp_path):
    # Extensionless file with JSON content -> auto-detected.
    f = tmp_path / "spec"
    f.write_text(json.dumps(SPEC), encoding="utf-8")
    assert load_spec(str(f))["info"]["title"] == "Shop API"


def test_load_spec_local_yaml(tmp_path):
    f = tmp_path / "spec.yaml"
    f.write_text("openapi: 3.0.0\ninfo:\n  title: YamlApi\n  version: '1'\npaths: {}\n", encoding="utf-8")
    assert load_spec(str(f))["info"]["title"] == "YamlApi"


def test_load_spec_from_url_is_fetched():
    class _Resp:
        def read(self):
            return json.dumps(SPEC).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=_Resp()) as m:
        spec = load_spec("https://api.example.com/openapi.json")
    assert m.called
    assert spec["info"]["title"] == "Shop API"
    assert len(parse_openapi(spec)) == 2
