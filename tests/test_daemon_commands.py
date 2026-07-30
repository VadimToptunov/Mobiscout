"""JSON-RPC daemon protocol + handlers — the plugin's bridge to the engine. The
device actions shell out, so they're driven through a mocked subprocess; no device
needed."""

from types import SimpleNamespace
from unittest import mock

import pytest

import framework.health.preflight as pf
from framework.cli.daemon_commands import JSONRPCServer, generate_selector
from framework.health.preflight import PreflightResult

_SUB = "framework.cli.daemon_commands.subprocess"


@pytest.fixture(autouse=True)
def _stub_preflight(monkeypatch):
    """session/start now runs a device-free preflight (env + Appium HTTP). Stub it
    green by default so the lifecycle/action tests don't reach a real Appium/adb/SDK;
    the preflight-specific tests override these."""
    monkeypatch.setattr(pf, "ensure_android_home", lambda: "/fake/sdk")
    monkeypatch.setattr(pf, "preflight", lambda platform, driver, server: [])


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


# ---- session/start preflight (fail-fast, device-free) ----


def test_session_start_preflight_fail_surfaces_actionable_error(server, monkeypatch):
    """A fail-level preflight (e.g. no ANDROID_HOME) blocks the session and the
    daemon surfaces the actionable fix through its normal error channel (-32603)."""
    fail = PreflightResult(
        "ANDROID_HOME",
        False,
        "fail",
        "No Android SDK found (ANDROID_HOME/ANDROID_SDK_ROOT unset)",
        fix="Install the Android SDK and set ANDROID_HOME to its path",
    )
    monkeypatch.setattr(pf, "preflight", lambda platform, driver, server: [fail])

    with pytest.raises(ValueError) as excinfo:
        server.handle_session_start({"device_id": "emulator-5554", "backend": "appium"})
    msg = str(excinfo.value)
    assert "ANDROID_HOME" in msg and "set ANDROID_HOME" in msg
    assert server.sessions == {}  # nothing stored on a hard failure

    # And the JSON-RPC layer wraps it as an internal error carrying the fix text.
    resp = server.handle_request(
        {"jsonrpc": "2.0", "id": 9, "method": "session/start", "params": {"backend": "appium"}}
    )
    assert resp["error"]["code"] == -32603 and "ANDROID_HOME" in resp["error"]["message"]


def test_session_start_all_pass_starts_and_attaches_warnings(server, monkeypatch):
    """All-pass/warn preflight starts the session normally; warns ride along as a
    ``warnings`` list rather than blocking. ensure_android_home is invoked."""
    called = {"ensured": False}

    def _ensure():
        called["ensured"] = True
        return "/fake/sdk"

    warn = PreflightResult(
        "Appium driver: uiautomator2",
        True,
        "warn",
        "Required Appium driver 'uiautomator2' is not installed",
        fix="appium driver install uiautomator2",
    )
    monkeypatch.setattr(pf, "ensure_android_home", _ensure)
    monkeypatch.setattr(pf, "preflight", lambda platform, driver, server: [warn])

    resp = server.handle_session_start({"device_id": "emulator-5554", "backend": "appium"})
    assert called["ensured"] is True
    assert resp["session_id"] in server.sessions
    assert resp["warnings"] and "uiautomator2" in resp["warnings"][0]


def test_session_start_clean_pass_has_no_warnings(server, monkeypatch):
    monkeypatch.setattr(pf, "preflight", lambda platform, driver, server: [])
    resp = server.handle_session_start({"device_id": "emulator-5554", "backend": "appium"})
    assert "warnings" not in resp


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


# ---- app/install + app/uninstall (delegate to DeviceManager) ----


def test_app_install_dispatches_to_device_manager(server):
    with mock.patch.object(
        server.device_manager, "install_app", return_value={"ok": True, "detail": "installed"}
    ) as inst:
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "app/install",
                "params": {"platform": "android", "device_id": "emulator-5554", "app_path": "/tmp/app.apk"},
            }
        )
    assert resp["result"] == {"ok": True, "detail": "installed"}
    inst.assert_called_once_with("android", "emulator-5554", "/tmp/app.apk")


def test_app_install_without_app_path_is_rpc_error(server):
    resp = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "app/install",
            "params": {"platform": "android", "device_id": "emulator-5554"},
        }
    )
    assert resp["error"]["code"] == -32603 and "app_path" in resp["error"]["message"]


def test_app_install_surfaces_failure_result(server):
    with mock.patch.object(server.device_manager, "install_app", return_value={"ok": False, "detail": "offline"}):
        resp = server.handle_app_install(
            {"platform": "android", "device_id": "emulator-5554", "app_path": "/tmp/app.apk"}
        )
    assert resp == {"ok": False, "detail": "offline"}


def test_app_uninstall_dispatches_to_device_manager(server):
    with mock.patch.object(
        server.device_manager, "uninstall_app", return_value={"ok": True, "detail": "uninstalled"}
    ) as uninst:
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "app/uninstall",
                "params": {"platform": "ios", "device_id": "AAA", "package": "com.x"},
            }
        )
    assert resp["result"] == {"ok": True, "detail": "uninstalled"}
    uninst.assert_called_once_with("ios", "AAA", "com.x")


def test_app_uninstall_without_package_is_rpc_error(server):
    resp = server.handle_request(
        {"jsonrpc": "2.0", "id": 23, "method": "app/uninstall", "params": {"platform": "android"}}
    )
    assert resp["error"]["code"] == -32603 and "package" in resp["error"]["message"]


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
