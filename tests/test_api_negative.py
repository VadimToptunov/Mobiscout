"""Negative-security API tests generated from captured traffic (fuzzer #2): missing-token,
BOLA/IDOR, missing-field — as runnable pytest, with NO captured credentials baked in."""

import ast
from types import SimpleNamespace

from framework.codegen.api_negative import emit_api_negative_tests


def _call(method, url, headers=None, body=None):
    return SimpleNamespace(method=method, url=url, request_headers=headers or {}, request_body=body)


def test_missing_token_case_for_authed_endpoint():
    calls = [_call("GET", "https://api.x.com/v1/orders", headers={"Authorization": "Bearer SECRET123"})]
    files = emit_api_negative_tests(calls)
    src = files["test_api_security.py"]
    assert "_requires_auth" in src
    assert "401, 403" in src
    # the captured token must NOT appear in the generated file
    assert "SECRET123" not in src
    ast.parse(src)  # valid Python


def test_bola_case_swaps_a_numeric_object_id():
    calls = [_call("GET", "https://api.x.com/v1/users/42/profile", headers={"Authorization": "t"})]
    src = emit_api_negative_tests(calls)["test_api_security.py"]
    assert "_rejects_foreign_object_id" in src
    assert "/v1/users/43/profile" in src  # id bumped 42 -> 43
    assert "!= 200" in src


def test_missing_field_case_for_json_post():
    calls = [
        _call(
            "POST",
            "https://api.x.com/v1/login",
            headers={"Authorization": "t"},
            body='{"username": "u", "password": "p"}',
        )
    ]
    src = emit_api_negative_tests(calls)["test_api_security.py"]
    assert "rejects_missing_username" in src
    assert "400 <= r.status_code < 500" in src
    ast.parse(src)


def test_no_cases_without_auth_id_or_body():
    # A plain unauthenticated GET with no id and no body yields nothing to test.
    assert emit_api_negative_tests([_call("GET", "https://api.x.com/health")]) == {}


def test_auth_token_read_from_env_not_hardcoded():
    calls = [
        _call("POST", "https://api.x.com/v1/items/7", headers={"Authorization": "Bearer LEAKME"}, body='{"name": "x"}')
    ]
    src = emit_api_negative_tests(calls)["test_api_security.py"]
    assert "os.environ.get('MOBISCOUT_API_TOKEN'" in src
    assert "LEAKME" not in src  # captured secret never baked in
