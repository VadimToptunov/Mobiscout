"""The MCP stdio server: the JSON-RPC dispatch (initialize / tools/list / tools/call /
ping / notifications) and the device-free tools (list_targets, generate_tests)."""

import io
import json

from framework.codegen.ir import ActionType, Platform, Selector, SelectorStrategy, Step, TestCase, TestModel
from framework.mcp.server import PROTOCOL_VERSION, TOOLS, handle_message, serve_stdio


def _model_dict():
    model = TestModel(
        name="LoginFlow",
        app_package="com.example.app",
        platform=Platform.ANDROID,
        cases=[
            TestCase(
                name="login",
                steps=[
                    Step(ActionType.LAUNCH),
                    Step(ActionType.TAP, selector=Selector(SelectorStrategy.ID, "login_btn")),
                ],
            )
        ],
    )
    return model.to_dict()


def _call(name, arguments):
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    )
    return resp["result"]


def test_initialize_reports_capabilities_and_server_info():
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    )
    result = resp["result"]
    assert result["protocolVersion"] == "2025-06-18"  # echoes the client's version
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "mobiscout"


def test_initialize_defaults_protocol_when_client_omits_it():
    resp = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["result"]["protocolVersion"] == PROTOCOL_VERSION


def test_notifications_get_no_response():
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_ping():
    assert handle_message({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}


def test_unknown_method_is_a_protocol_error():
    resp = handle_message({"jsonrpc": "2.0", "id": 3, "method": "does/not/exist"})
    assert resp["error"]["code"] == -32601


def test_tools_list_advertises_the_tools():
    resp = handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"list_targets", "generate_tests", "crawl_app"}
    # Every advertised tool has a JSON-Schema input contract.
    for t in TOOLS:
        assert t["inputSchema"]["type"] == "object"


def test_list_targets_tool_includes_maestro_and_pytest():
    result = _call("list_targets", {})
    assert result["isError"] is False
    data = json.loads(result["content"][0]["text"])
    ids = {t["id"] for t in data["targets"]}
    assert {"python_pytest", "maestro"} <= ids


def test_generate_tests_emits_source_for_requested_targets():
    result = _call("generate_tests", {"model": _model_dict(), "targets": ["python_pytest", "maestro"]})
    assert result["isError"] is False
    files = json.loads(result["content"][0]["text"])["files"]
    assert set(files) == {"python_pytest", "maestro"}
    # The maestro flow is real YAML content; the pytest file is real Python.
    assert any(name.endswith(".yaml") for name in files["maestro"])
    assert any("def test_" in content for content in files["python_pytest"].values())


def test_generate_tests_defaults_to_pytest():
    result = _call("generate_tests", {"model": _model_dict()})
    files = json.loads(result["content"][0]["text"])["files"]
    assert set(files) == {"python_pytest"}


def test_generate_tests_rejects_unknown_target():
    result = _call("generate_tests", {"model": _model_dict(), "targets": ["cobol_selenium"]})
    assert result["isError"] is True
    assert "Unknown target" in result["content"][0]["text"]


def test_generate_tests_requires_a_model():
    result = _call("generate_tests", {"targets": ["python_pytest"]})
    assert result["isError"] is True
    assert "`model` is required" in result["content"][0]["text"]


def test_crawl_app_requires_a_package():
    result = _call("crawl_app", {"platform": "android"})
    assert result["isError"] is True
    assert "`package`" in result["content"][0]["text"]


def test_unknown_tool_is_an_error_result_not_a_crash():
    result = _call("nope", {})
    assert result["isError"] is True


def test_serve_stdio_rejects_an_oversized_line():
    from framework.mcp.server import _MAX_MESSAGE_BYTES

    huge = '{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"' + "a" * (_MAX_MESSAGE_BYTES) + '"}}'
    out = io.StringIO()
    serve_stdio(stdin=io.StringIO(huge), stdout=out)
    resp = json.loads(out.getvalue().splitlines()[-1])
    assert resp["error"]["code"] == -32600  # rejected before parsing, like the daemon's cap


def test_serve_stdio_roundtrips_newline_delimited_json():
    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),  # no reply
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            "not json",  # -> parse error response
        ]
    )
    out = io.StringIO()
    serve_stdio(stdin=io.StringIO(requests), stdout=out)
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    # initialize reply, tools/list reply, parse-error reply — the notification produced nothing.
    assert [m.get("id") for m in lines] == [1, 2, None]
    assert lines[-1]["error"]["code"] == -32700
