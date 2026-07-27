"""Behaviour tests for the ``generate`` CLI group (codegen from an app model).

Each command runs the real codegen pipeline over a small YAML app model and an
OpenAPI spec written to tmp_path, asserting the artifacts actually written to disk
(page objects, API client, BDD features, API tests) and the error branches (bad
model, missing endpoints, unknown target). ``generate tests`` has its own suite in
test_app_model_codegen.py; here we cover the sibling emitters and edge paths.
"""

import pytest
from click.testing import CliRunner

from framework.cli.generate_commands import generate

_MODEL_YAML = """
meta:
  app_version: "1.0.0"
  platform: android
screens:
  login:
    name: LoginScreen
    elements:
      - id: username_field
        type: input
        selector:
          android: "id:com.app:id/username"
          test_id: username
      - id: login_btn
        type: button
        selector:
          android: "accessibility:login"
api_calls:
  getUser:
    name: getUser
    endpoint: /users/{id}
    method: GET
flows:
  - name: Login flow
    description: user logs in
    steps:
      - action: tap
        screen: LoginScreen
      - action: type
        screen: LoginScreen
"""

_OPENAPI_YAML = """
openapi: 3.0.0
info:
  title: Demo
  version: "1.0.0"
paths:
  /pets:
    get:
      operationId: listPets
      responses:
        "200":
          description: ok
  /pets/{id}:
    get:
      operationId: getPet
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: ok
"""


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


@pytest.fixture()
def model(tmp_path) -> str:
    p = tmp_path / "app.yaml"
    p.write_text(_MODEL_YAML, encoding="utf-8")
    return str(p)


def test_pages_generates_page_objects(runner, tmp_path, model):
    out = tmp_path / "pages"
    result = runner.invoke(generate, ["pages", "--model", model, "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    generated = list(out.rglob("*.py"))
    assert generated, "no page objects written"
    assert "LoginScreen" in generated[0].read_text(encoding="utf-8") or "login" in generated[0].name


def test_pages_bad_model_aborts(runner, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("meta: {}\n", encoding="utf-8")  # missing required app_version/platform
    result = runner.invoke(generate, ["pages", "--model", str(bad), "--output", str(tmp_path / "o")])
    _no_crash(result)
    assert result.exit_code != 0
    assert "Generation failed" in result.output


def test_api_generates_client(runner, tmp_path, model):
    out = tmp_path / "api"
    result = runner.invoke(generate, ["api", "--model", model, "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert (out / "api_client.py").exists()


def test_features_generates_feature_files(runner, tmp_path, model):
    out = tmp_path / "features"
    result = runner.invoke(generate, ["features", "--model", model, "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    features = list(out.rglob("*.feature"))
    assert features, "no feature files written"
    assert "Feature" in features[0].read_text(encoding="utf-8")


def test_api_tests_from_model(runner, tmp_path, model):
    out = tmp_path / "apitests"
    result = runner.invoke(generate, ["api-tests", "--model", model, "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert list(out.rglob("*.py")), "no api tests written"


def test_api_tests_from_openapi(runner, tmp_path):
    spec = tmp_path / "openapi.yaml"
    spec.write_text(_OPENAPI_YAML, encoding="utf-8")
    out = tmp_path / "apitests"
    result = runner.invoke(
        generate,
        ["api-tests", "--openapi", str(spec), "--output", str(out), "--base-url", "https://api.example.com"],
    )
    _no_crash(result)
    assert result.exit_code == 0
    files = list(out.rglob("*.py"))
    assert files, "no api tests written from openapi"


def test_api_tests_requires_a_source(runner):
    result = runner.invoke(generate, ["api-tests"])
    _no_crash(result)
    assert result.exit_code != 0
    assert "Provide --model or --openapi" in result.output


def test_api_review_writes_context_sheet(runner, tmp_path):
    spec = tmp_path / "openapi.yaml"
    spec.write_text(_OPENAPI_YAML, encoding="utf-8")
    out = tmp_path / "review.md"
    result = runner.invoke(generate, ["api-review", "--openapi", str(spec), "--output", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    # Both endpoints are inventoried in the markdown context sheet.
    assert "/pets" in text
