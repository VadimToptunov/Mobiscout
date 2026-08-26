"""DeviceManager boot/shutdown control (list AVDs, start/stop emulator &
simulator) and its daemon routing. Shells out, so tests drive it through mocked
subprocess — no real device."""

import subprocess
from types import SimpleNamespace
from unittest import mock

from framework.cli.daemon_commands import JSONRPCServer
from framework.devices.device_manager import DeviceManager

_MOD = "framework.devices.device_manager.subprocess"


def _still_running(popen):
    """Make a mocked Popen behave like an emulator that is still booting."""
    popen.return_value.wait.side_effect = subprocess.TimeoutExpired("emulator", 1.5)


def test_list_avds_parses_lines():
    with mock.patch(f"{_MOD}.run", return_value=SimpleNamespace(returncode=0, stdout="Pixel_7\nPixel_3a_API_34\n\n")):
        assert DeviceManager.list_avds() == ["Pixel_7", "Pixel_3a_API_34"]


def test_list_avds_drops_emulator_info_diagnostics():
    """Emulator 34.x/35.x print an INFO line on stdout; only AVD-name-shaped lines
    may be listed, or the plugin offers the diagnostic as a bootable target."""
    stdout = "INFO    | Storing crashdata in: /tmp/crash, detection is enabled\nPixel_7\n"
    with mock.patch(f"{_MOD}.run", return_value=SimpleNamespace(returncode=0, stdout=stdout)):
        assert DeviceManager.list_avds() == ["Pixel_7"]


def test_list_avds_empty_when_emulator_absent():
    with mock.patch(f"{_MOD}.run", side_effect=FileNotFoundError):
        assert DeviceManager.list_avds() == []


def test_start_android_launches_detached():
    with mock.patch(f"{_MOD}.Popen") as popen:
        _still_running(popen)
        result = DeviceManager.start_device("android", "Pixel_7")
    assert result == {"started": True, "platform": "android", "target": "Pixel_7", "status": "starting"}
    args = popen.call_args[0][0]
    assert args[:2] == ["emulator", "-avd"] and args[2] == "Pixel_7"


def test_start_android_reports_an_emulator_that_died_immediately():
    """An unknown/locked AVD kills the emulator in milliseconds; reporting
    started=True there leaves the caller waiting for a device that never appears."""

    def popen(cmd, stdout=None, stderr=None):
        # The emulator logs this on stdout on current versions, stderr on older ones.
        stdout.write("INFO | Android emulator version 36.6.11.0\n")
        stdout.write("ERROR | Unknown AVD name [Ghost], use -list-avds to see valid list.\n")
        return SimpleNamespace(wait=lambda timeout: 1, returncode=1)

    with mock.patch(f"{_MOD}.Popen", side_effect=popen):
        result = DeviceManager.start_device("android", "Ghost")
    assert result["started"] is False
    assert "Unknown AVD name" in result["error"]


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


def test_stop_ios_already_shutdown_is_success():
    """simctl exits non-zero when the simulator is already off — the desired state
    holds, so a second Stop must not surface an error."""
    stderr = "An error was encountered processing the command (domain=com.apple.CoreSimulator.SimError, code=405): "
    stderr += "Unable to shutdown device in current state: Shutdown"
    with mock.patch(f"{_MOD}.run", return_value=SimpleNamespace(returncode=149, stderr=stderr)):
        assert DeviceManager.stop_device("ios", "UDID-1")["stopped"] is True


def test_stop_timeout_is_handled():
    with mock.patch(f"{_MOD}.run", side_effect=subprocess.TimeoutExpired("adb", 15)):
        assert DeviceManager.stop_device("android", "emulator-5554")["stopped"] is False


def test_daemon_routes_device_control():
    srv = JSONRPCServer()
    for m in ("device/start", "device/stop", "device/listAvds"):
        assert m in srv.handlers

    with mock.patch(f"{_MOD}.Popen") as popen:
        _still_running(popen)
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
