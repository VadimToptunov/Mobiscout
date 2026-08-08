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


def test_process_line_handles_request_blank_and_parse_error(server):
    """The shared line handler (used by both stdio and TCP) frames a valid
    request, ignores blank lines, and turns malformed JSON into a -32700."""
    import json as _json

    ok = server._process_line('{"jsonrpc": "2.0", "id": 1, "method": "health/check"}')
    assert _json.loads(ok)["id"] == 1

    assert server._process_line("   \n") is None  # blank -> nothing to send

    bad = server._process_line("{not json")
    assert _json.loads(bad)["error"]["code"] == -32700


def test_tcp_transport_serves_a_request(server):
    """--tcp now actually serves: connect, read the ready notification, send a
    request, get its response — same framing as stdio."""
    import socket
    import threading
    import json as _json

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # a free port

    threading.Thread(target=server.run_tcp, args=(port,), daemon=True).start()

    deadline = 2.0
    conn = None
    while deadline > 0 and conn is None:
        try:
            conn = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        except OSError:
            import time

            time.sleep(0.05)
            deadline -= 0.05
    assert conn is not None, "TCP server never started listening"

    with conn, conn.makefile("rwb") as stream:
        ready = _json.loads(stream.readline().decode("utf-8"))
        assert ready["method"] == "notification/ready"
        stream.write(b'{"jsonrpc": "2.0", "id": 7, "method": "health/check"}\n')
        stream.flush()
        resp = _json.loads(stream.readline().decode("utf-8"))
    assert resp["id"] == 7 and "error" not in resp


def test_license_status_defaults_to_unlimited(server):
    """The open-core engine has no paid provider — license/status reports the
    fully-unlocked default so the IDE shows no quota."""
    import framework.licensing as lic

    lic.reset_provider()
    resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "license/status"})
    result = resp["result"]
    assert result["unlimited"] is True
    assert result["max_screens"] is None and result["max_tests"] is None


def test_license_status_reflects_an_installed_free_tier(server):
    """Once a paid layer installs a FREE (quota) provider, the IDE sees the tier
    and its limits verbatim."""
    import framework.licensing as lic

    lic.set_provider(lambda: lic.Entitlements(tier=lic.Tier.FREE, max_screens=15, max_tests=40, max_targets=2))
    try:
        result = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "license/status"})["result"]
    finally:
        lic.reset_provider()
    assert result["tier"] == "free" and result["unlimited"] is False
    assert result["max_screens"] == 15 and result["max_tests"] == 40 and result["max_targets"] == 2


def test_activate_pro_layer_never_raises():
    """The daemon's PRO bootstrap is best-effort: whether or not the paid layer is
    installed, activating it must never raise (a load failure can't stop the
    daemon). On a plain engine it's a no-op and the tier stays UNLIMITED."""
    import framework.licensing as lic
    from framework.cli.daemon_commands import _activate_pro_layer

    lic.reset_provider()
    try:
        _activate_pro_layer()  # must not raise, regardless of environment
    finally:
        lic.reset_provider()  # undo any provider it installed, for later tests


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


def _fake_png(width: int, height: int) -> bytes:
    """A byte string with a valid PNG signature + IHDR width/height — enough for
    the dimension parser (the pixel data is irrelevant here)."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00rest"
    )


def test_screenshot_reports_real_png_dimensions(server, tmp_path):
    """The screenshot RPC must report the capture's actual size (read from the
    PNG header), not the old hardcoded 1080x2400."""
    sid = _session(server)
    png = _fake_png(1170, 2532)  # e.g. an iPhone, not 1080x2400
    with mock.patch(f"{_SUB}.run", return_value=SimpleNamespace(returncode=0, stdout=png)):
        with mock.patch("builtins.open", mock.mock_open(read_data=png)):
            resp = server.handle_get_screenshot({"session_id": sid, "format": "png"})
    assert resp["format"] == "png"
    assert resp["width"] == 1170 and resp["height"] == 2532


def test_png_dimensions_parses_header_and_falls_back():
    from framework.cli.daemon_commands import _png_dimensions

    assert _png_dimensions(_fake_png(1080, 1920)) == (1080, 1920)
    assert _png_dimensions(b"not a png at all") == (0, 0)  # unknown, never raises


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


# ---- app-log streaming (logs/start, logs/stop) ----


def test_logs_start_requires_udid_or_session(server):
    with pytest.raises(ValueError):
        server.handle_logs_start({})


def test_logs_start_streams_filtered_process_and_stop_terminates(server):
    """logs/start spawns a `simctl log stream` filtered to the app process and
    returns streaming state; logs/stop terminates it. The process defaults to the
    bundle-id's last component."""
    fake_proc = mock.Mock()
    fake_proc.stdout = iter([])  # the pump thread finds no lines and exits at once
    with mock.patch(_SUB) as sub:
        sub.Popen.return_value = fake_proc
        res = server.handle_logs_start({"udid": "UDID-123", "bundle_id": "com.acme.ChaosBank"})
        assert res == {"streaming": True, "udid": "UDID-123", "platform": "ios", "process": "ChaosBank"}
        cmd = sub.Popen.call_args[0][0]
        assert "log" in cmd and "stream" in cmd
        assert 'process == "ChaosBank"' in cmd
    server.handle_logs_stop({})
    fake_proc.terminate.assert_called_once()


def test_logs_start_derives_udid_and_process_from_session(server):
    server.sessions["s1"] = {"device_id": "UDID-9", "bundle_id": "io.x.MyApp"}
    fake_proc = mock.Mock()
    fake_proc.stdout = iter([])
    with mock.patch(_SUB) as sub:
        sub.Popen.return_value = fake_proc
        res = server.handle_logs_start({"session_id": "s1"})
    assert res["udid"] == "UDID-9" and res["process"] == "MyApp"
    server.handle_logs_stop({})


def test_logs_start_android_uses_adb_logcat_scoped_to_pid(server, monkeypatch):
    """Android streams via `adb logcat`, scoped to the app's PID when running."""
    monkeypatch.setattr(JSONRPCServer, "_android_pid", staticmethod(lambda serial, pkg: "4242"))
    fake_proc = mock.Mock()
    fake_proc.stdout = iter([])
    with mock.patch(_SUB) as sub:
        sub.Popen.return_value = fake_proc
        res = server.handle_logs_start(
            {"udid": "emulator-5554", "bundle_id": "com.acme.app", "platform": "android"}
        )
        assert res["platform"] == "android"
        cmd = sub.Popen.call_args[0][0]
        assert cmd[:3] == ["adb", "-s", "emulator-5554"]
        assert "logcat" in cmd and "--pid" in cmd and "4242" in cmd
    server.handle_logs_stop({})
