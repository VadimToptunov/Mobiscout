"""Tests for the codegen API-client and BDD-feature emitters (replacing generators/)."""

import py_compile

from framework.codegen.api_client import emit_api_client
from framework.codegen.bdd_feature import emit_feature_files
from framework.model.app_model import AppModel, AppModelMeta
from framework.model.api import APICall
from framework.model.flow import Flow
from framework.model.enums import Platform


def _model() -> AppModel:
    return AppModel(
        meta=AppModelMeta(app_version="1.0.0", platform=Platform.ANDROID),
        api_calls={
            "auth_login": APICall(
                name="auth_login",
                endpoint="/api/v1/auth/login",
                method="POST",
                request_schema={"username": "string", "password": "string"},
            )
        },
        flows=[
            Flow(
                name="Login Flow", description="User logs in", steps=[{"screen": "LoginScreen", "action": "tap login"}]
            )
        ],
    )


def test_api_client_compiles_with_endpoint_method(tmp_path):
    out = emit_api_client(_model())
    assert list(out) == ["api_client.py"]
    content = out["api_client.py"]
    assert "class APIClient:" in content
    assert "def auth_login(self, username: Any = None, password: Any = None)" in content
    assert 'self._request("POST", "/api/v1/auth/login", json=payload)' in content
    f = tmp_path / "api_client.py"
    f.write_text(content, encoding="utf-8", newline="\n")
    py_compile.compile(str(f), doraise=True)


def test_api_client_empty_when_no_calls():
    m = AppModel(meta=AppModelMeta(app_version="1.0.0", platform=Platform.ANDROID))
    assert emit_api_client(m) == {}


def test_feature_file_renders_gherkin():
    out = emit_feature_files(_model())
    assert list(out) == ["login_flow.feature"]
    feature = out["login_flow.feature"]
    assert feature.startswith("Feature: Login Flow")
    assert "Scenario: Login Flow" in feature
    assert 'When tap login on "LoginScreen"' in feature
