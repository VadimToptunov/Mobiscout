"""Static source → API tests bridge: the analyzers discover the endpoints an app
calls; this maps them onto the codegen model so `generate api-tests --source`
produces tests from the app's own code (not only a user-supplied OpenAPI spec)."""

import py_compile
from types import SimpleNamespace

from framework.codegen.api_test import emit_api_tests
from framework.codegen.source_api_adapter import (
    contracts_to_api_calls,
    endpoints_to_api_calls,
    source_api_calls,
)


def _ep(method, path, function_name="", request_type=None, response_type=None):
    return SimpleNamespace(
        method=method,
        path=path,
        function_name=function_name,
        request_type=request_type,
        response_type=response_type,
    )


def test_endpoints_map_to_api_calls():
    calls = endpoints_to_api_calls([_ep("GET", "/accounts/{id}", "getAccount"), _ep("post", "/transfers", "transfer")])
    assert [(c.name, c.method, c.endpoint) for c in calls] == [
        ("getAccount", "GET", "/accounts/{id}"),
        ("transfer", "POST", "/transfers"),
    ]


def test_endpoint_names_are_deduped():
    # Two endpoints with the same function name must both survive (names are keys).
    calls = endpoints_to_api_calls([_ep("GET", "/a", "load"), _ep("GET", "/b", "load")])
    assert [c.name for c in calls] == ["load", "load_2"]
    assert {c.endpoint for c in calls} == {"/a", "/b"}


def test_endpoint_without_function_name_gets_a_derived_name():
    (call,) = endpoints_to_api_calls([_ep("DELETE", "/sessions/{sid}")])
    assert call.method == "DELETE" and call.endpoint == "/sessions/{sid}"
    assert call.name  # derived, non-empty


def test_contracts_carry_schemas_and_responses():
    contract = SimpleNamespace(
        method="POST",
        endpoint="/login",
        request_schema={"user": "string", "pass": "string"},
        response_schema={"token": "string"},
        error_responses=[{"status": 401}],
    )
    (call,) = contracts_to_api_calls([contract])
    assert call.method == "POST" and call.endpoint == "/login"
    assert call.request_schema == {"user": "string", "pass": "string"}
    assert {"status": 200, "schema": {"token": "string"}} in call.responses
    assert {"status": 401} in call.responses


def test_source_to_runnable_api_tests_end_to_end(tmp_path):
    """The headline flow: real Kotlin Retrofit source -> APICalls -> a runnable
    test_api.py that imports the endpoints and compiles."""
    (tmp_path / "BankApi.kt").write_text(
        """
        interface BankApi {
            @GET("/accounts/{id}")
            suspend fun getAccount(@Path("id") id: String): Account

            @POST("/transfers")
            suspend fun transfer(@Body req: TransferRequest): TransferResult
        }
        """,
        encoding="utf-8",
    )

    calls = source_api_calls(str(tmp_path))
    by_endpoint = {c.endpoint: c for c in calls}
    assert "/accounts/{id}" in by_endpoint and by_endpoint["/accounts/{id}"].method == "GET"
    assert "/transfers" in by_endpoint and by_endpoint["/transfers"].method == "POST"

    app_model = SimpleNamespace(api_calls={c.name: c for c in calls})
    files = emit_api_tests(app_model, base_url="https://api.example.com")
    assert files, "no API tests generated from source"

    test_src = next(iter(files.values()))
    assert "/accounts/1" in test_src  # path param substituted
    assert "/transfers" in test_src

    out = tmp_path / "test_api.py"
    out.write_text(test_src, encoding="utf-8", newline="\n")
    py_compile.compile(str(out), doraise=True)  # generated source is valid Python
