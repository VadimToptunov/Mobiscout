"""Tests for the codegen API-test emitter."""

import py_compile

from framework.codegen.api_test import emit_api_tests
from framework.model.api import APICall
from framework.model.app_model import AppModel, AppModelMeta
from framework.model.enums import Platform


def _model(calls):
    return AppModel(
        meta=AppModelMeta(app_version="1.0.0", platform=Platform.ANDROID),
        api_calls={c.name: c for c in calls},
    )


def test_emits_one_test_per_endpoint_and_compiles(tmp_path):
    model = _model(
        [
            APICall(name="list_cards", endpoint="/api/cards", method="GET"),
            APICall(
                name="login",
                endpoint="/api/auth/login",
                method="POST",
                request_schema={"username": "string", "password": "string"},
            ),
            APICall(name="block_card", endpoint="/api/cards/{card_id}/block", method="POST"),
        ]
    )
    out = emit_api_tests(model, base_url="http://localhost:9000")
    content = out["test_api.py"]
    assert content.count("def test_") == 3
    assert "def test_list_cards" in content
    assert 'session.get(BASE_URL + "/api/cards")' in content
    # POST carries a JSON body built from the request schema
    assert "'username': 'test'" in content and "session.post" in content
    # path params substituted
    assert "/api/cards/1/block" in content
    f = tmp_path / "test_api.py"
    f.write_text(content, encoding="utf-8", newline="\n")
    py_compile.compile(str(f), doraise=True)


def test_no_api_calls_emits_nothing():
    assert emit_api_tests(_model([])) == {}
