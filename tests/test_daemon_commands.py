"""JSON-RPC daemon protocol + handlers — the plugin's bridge to the engine. The
device actions shell out, so they're driven through a mocked subprocess; no device
needed."""

from types import SimpleNamespace
from unittest import mock

import pytest

from framework.cli.daemon_commands import JSONRPCServer, generate_selector

_SUB = "framework.cli.daemon_commands.subprocess"


@pytest.fixture()
def server():
    return JSONRPCServer()


# ---- protocol ----


def test_rejects_wrong_jsonrpc_version(server):
    resp = server.handle_request({"jsonrpc": "1.0", "id": 1, "method": "health/check"})
    assert resp["error"]["code"] == -32600


def test_unknown_method(server):
    resp = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "does/notExist", "params": {}})
    assert resp["error"]["code"] == -32601


def test_handler_exception_becomes_internal_error(server):
    # flow/getGraph without 'package' raises ValueError inside the handler.
    resp = server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "flow/getGraph", "params": {}})
    assert resp["error"]["code"] == -32603


def test_health_and_backend_list(server):
    health = server.handle_request({"jsonrpc": "2.0", "id": 4, "method": "health/check", "params": {}})
    assert health["result"]["status"] == "ok"
    backends = server.handle_request({"jsonrpc": "2.0", "id": 5, "method": "backend/list", "params": {}})
    names = {b["name"] for b in backends["result"]["backends"]}
    assert {"appium", "uiautomator2", "xcuitest"} <= names


# ---- session lifecycle + device actions (mocked subprocess) ----


def _session(server, device_id="emulator-5554"):
    return server.handle_session_start({"device_id": device_id, "backend": "appium"})["session_id"]


def test_session_start_stop(server):
    sid = _session(server)
    assert sid in server.sessions
    assert server.handle_session_stop({"session_id": sid})["status"] == "stopped"
    assert sid not in server.sessions


def test_actions_require_a_known_session(server):
    for method in ("handle_tap", "handle_swipe", "handle_type"):
        with pytest.raises(Exception):
            getattr(server, method)({"session_id": "ghost"})


def test_tap_shells_out_to_adb(server):
    sid = _session(server)
    with mock.patch(f"{_SUB}.run") as run:
        resp = server.handle_tap({"session_id": sid, "x": 10, "y": 20})
    assert resp["status"] == "success"
    assert run.call_args[0][0][:4] == ["adb", "-s", "emulator-5554", "shell"]


def test_type_escapes_spaces(server):
    sid = _session(server)
    with mock.patch(f"{_SUB}.run") as run:
        server.handle_type({"session_id": sid, "text": "hello world"})
    assert "hello%sworld" in run.call_args[0][0]


def test_swipe_passes_coordinates(server):
    sid = _session(server)
    with mock.patch(f"{_SUB}.run") as run:
        resp = server.handle_swipe(
            {"session_id": sid, "start_x": 1, "start_y": 2, "end_x": 3, "end_y": 4, "duration_ms": 200}
        )
    assert resp["status"] == "success"
    assert run.call_args[0][0][-5:] == ["1", "2", "3", "4", "200"]


def test_screenshot_encodes_capture(server, tmp_path):
    sid = _session(server)
    png = b"\x89PNG\r\n\x1a\n' fake"
    with mock.patch(f"{_SUB}.run", return_value=SimpleNamespace(returncode=0, stdout=png)):
        with mock.patch("builtins.open", mock.mock_open(read_data=png)):
            resp = server.handle_get_screenshot({"session_id": sid, "format": "png"})
    assert resp["format"] == "png" and resp["width"] > 0


# ---- selector/generate (pure) ----

_XML = (
    '<hierarchy><node class="android.widget.Button" resource-id="com.x:id/ok" text="OK" '
    'content-desc="" clickable="true" bounds="[0,0][100,50]" package="com.x"/></hierarchy>'
)


def test_generate_selector_from_point():
    out = generate_selector({"source": _XML, "x": 50, "y": 25})
    assert out["found"] and out["selector"]["value"] == "com.x:id/ok"


def test_generate_selector_from_element_attrs():
    out = generate_selector({"element": {"resource_id": "com.x:id/login", "clickable": True, "class": "Button"}})
    assert out["found"] and out["selector"]["value"] == "com.x:id/login"


def test_generate_selector_off_target_is_not_found():
    out = generate_selector({"source": _XML, "x": 999, "y": 999})
    assert out["found"] is False


def test_generate_selector_bad_params():
    with pytest.raises(ValueError):
        generate_selector({})
