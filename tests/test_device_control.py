"""DeviceManager boot/shutdown control (list AVDs, start/stop emulator &
simulator) and its daemon routing. Shells out, so tests drive it through mocked
subprocess — no real device."""

import subprocess
from types import SimpleNamespace
from unittest import mock

from framework.cli.daemon_commands import JSONRPCServer
from framework.devices.device_manager import DeviceManager

_MOD = "framework.devices.device_manager.subprocess"


def test_list_avds_parses_lines():
    with mock.patch(f"{_MOD}.run", return_value=SimpleNamespace(returncode=0, stdout="Pixel_7\nPixel_3a_API_34\n\n")):
        assert DeviceManager.list_avds() == ["Pixel_7", "Pixel_3a_API_34"]


def test_list_avds_empty_when_emulator_absent():
    with mock.patch(f"{_MOD}.run", side_effect=FileNotFoundError):
        assert DeviceManager.list_avds() == []


def test_start_android_launches_detached():
    with mock.patch(f"{_MOD}.Popen") as popen:
        result = DeviceManager.start_device("android", "Pixel_7")
    assert result == {"started": True, "platform": "android", "target": "Pixel_7", "status": "starting"}
    args = popen.call_args[0][0]
    assert args[:2] == ["emulator", "-avd"] and args[2] == "Pixel_7"


def test_start_requires_target():
    assert DeviceManager.start_device("android", "")["started"] is False


def test_start_android_missing_binary_errors():
    with mock.patch(f"{_MOD}.Popen", side_effect=FileNotFoundError("no emulator")):
        result = DeviceManager.start_device("android", "Pixel_7")
    assert result["started"] is False and "no emulator" in result["error"]


def test_start_ios_boots():
    with mock.patch(f"{_MOD}.run", return_value=SimpleNamespace(returncode=0, stderr="")):
        result = DeviceManager.start_device("ios", "UDID-1")
    assert result == {"started": True, "platform": "ios", "target": "UDID-1", "status": "booted"}


def test_start_ios_already_booted_is_success():
    with mock.patch(
        f"{_MOD}.run",
        return_value=SimpleNamespace(returncode=1, stderr="Unable to boot device in current state: Booted"),
    ):
        assert DeviceManager.start_device("ios", "UDID-1")["started"] is True


def test_start_unsupported_platform():
    assert DeviceManager.start_device("windows", "x")["started"] is False


def test_stop_android_uses_adb_emu_kill():
    with mock.patch(f"{_MOD}.run", return_value=SimpleNamespace(returncode=0, stderr="")) as run:
        result = DeviceManager.stop_device("android", "emulator-5554")
    assert result["stopped"] is True
    assert run.call_args[0][0] == ["adb", "-s", "emulator-5554", "emu", "kill"]


def test_stop_ios_uses_simctl_shutdown():
    with mock.patch(f"{_MOD}.run", return_value=SimpleNamespace(returncode=0, stderr="")) as run:
        result = DeviceManager.stop_device("ios", "UDID-1")
    assert result["stopped"] is True
    assert run.call_args[0][0] == ["xcrun", "simctl", "shutdown", "UDID-1"]


def test_stop_requires_device_id_and_reports_failure():
    assert DeviceManager.stop_device("android", "")["stopped"] is False
    with mock.patch(f"{_MOD}.run", return_value=SimpleNamespace(returncode=1, stderr="not found")):
        result = DeviceManager.stop_device("android", "ghost")
    assert result["stopped"] is False and result["error"] == "not found"


def test_stop_timeout_is_handled():
    with mock.patch(f"{_MOD}.run", side_effect=subprocess.TimeoutExpired("adb", 15)):
        assert DeviceManager.stop_device("android", "emulator-5554")["stopped"] is False


def test_daemon_routes_device_control():
    srv = JSONRPCServer()
    for m in ("device/start", "device/stop", "device/listAvds"):
        assert m in srv.handlers

    with mock.patch(f"{_MOD}.Popen") as popen:
        resp = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "device/start",
                "params": {"platform": "android", "target": "Pixel_7"},
            }
        )
    assert resp["result"]["status"] == "starting" and popen.called

    with mock.patch(f"{_MOD}.run", return_value=SimpleNamespace(returncode=0, stdout="Pixel_7\n")):
        resp = srv.handle_request({"jsonrpc": "2.0", "id": 2, "method": "device/listAvds", "params": {}})
    assert resp["result"]["avds"] == ["Pixel_7"]
