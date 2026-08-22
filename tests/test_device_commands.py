"""Behaviour tests for the `mobiscout devices` CLI group (framework/cli/device_commands.py).

adb / xcrun simctl are the only true external I/O here, so `subprocess.run` in the
DeviceManager is faked with a dispatcher that emits realistic tool output. That
means the real DeviceManager parsing AND the CLI's filtering/summary/table logic
run for real — the tests assert on the rendered device inventory and on the
error/abort branches (unknown device, empty pool, cancelled delete).
"""

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from framework.devices import device_manager as dm
from framework.cli.device_commands import devices


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolate_pool_store(tmp_path, monkeypatch):
    """Redirect the persisted device-pool store to a per-test temp file, so pool CLI
    tests never read or write the real ~/.mobiscout/pools.json."""
    monkeypatch.setenv("MOBISCOUT_POOLS_PATH", str(tmp_path / "pools.json"))


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _ok(stdout="", stderr=""):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


_IOS_JSON = json.dumps(
    {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-17-0": [
                {"udid": "IOS-UDID-1", "name": "iPhone 15", "state": "Booted", "isAvailable": True}
            ]
        }
    }
)


def _fake_run_two_devices(cmd, **kwargs):
    """Simulate one online Android emulator and one booted iOS simulator."""
    if cmd[0] == "adb" and cmd[1] == "devices":
        return _ok("List of devices attached\nemulator-5554\tdevice product:sdk model:Pixel\n")
    if cmd[0] == "adb" and "ro.product.model" in cmd:
        return _ok("Pixel_6\n")
    if cmd[0] == "adb" and "ro.build.version.sdk" in cmd:
        return _ok("33\n")
    if cmd[0] == "xcrun" and "list" in cmd:
        return _ok(_IOS_JSON)
    return _ok("")


def _fake_run_no_devices(cmd, **kwargs):
    if cmd[0] == "adb" and cmd[1] == "devices":
        return _ok("List of devices attached\n")
    if cmd[0] == "xcrun":
        return _ok(json.dumps({"devices": {}}))
    return _ok("")


@pytest.fixture()
def two_devices(monkeypatch):
    monkeypatch.setattr(dm.subprocess, "run", _fake_run_two_devices)


@pytest.fixture()
def no_devices(monkeypatch):
    monkeypatch.setattr(dm.subprocess, "run", _fake_run_no_devices)


# --- list --------------------------------------------------------------------


def test_list_shows_both_platforms(runner, two_devices):
    result = runner.invoke(devices, ["list"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "emulator-5554" in result.output
    assert "iPhone 15" in result.output
    assert "Android: 1" in result.output
    assert "iOS: 1" in result.output
    assert "Total: 2" in result.output


def test_list_platform_filter(runner, two_devices):
    result = runner.invoke(devices, ["list", "--platform", "android"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "emulator-5554" in result.output
    assert "iPhone 15" not in result.output


def test_list_status_filter_no_match(runner, two_devices):
    # Real statuses are "online"/"booted"; none report as "available".
    result = runner.invoke(devices, ["list", "--status", "available"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No available devices found" in result.output


def test_list_no_devices(runner, no_devices):
    result = runner.invoke(devices, ["list"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No devices found" in result.output


# --- info --------------------------------------------------------------------


def test_info_found(runner, two_devices):
    result = runner.invoke(devices, ["info", "-d", "emulator-5554"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "emulator-5554" in result.output
    assert "android" in result.output


def test_info_not_found_aborts(runner, two_devices):
    result = runner.invoke(devices, ["info", "-d", "ghost-device"])
    _no_crash(result)
    assert result.exit_code != 0
    assert "not found" in result.output


# --- health ------------------------------------------------------------------


def test_health_all_healthy(runner, two_devices):
    result = runner.invoke(devices, ["health"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Healthy devices: 2" in result.output
    assert "100.0%" in result.output


def test_health_no_devices(runner, no_devices):
    result = runner.invoke(devices, ["health"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No devices found" in result.output


# --- pool --------------------------------------------------------------------


def test_pool_create_counts_known_devices(runner, two_devices):
    result = runner.invoke(devices, ["pool", "create", "-n", "p1", "-d", "emulator-5554,unknown"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Warning: Device unknown not found" in result.output
    assert "Created pool 'p1' with 1 devices" in result.output


def test_pool_list_empty(runner):
    result = runner.invoke(devices, ["pool", "list"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No device pools created" in result.output


def test_pool_info_missing_aborts(runner):
    result = runner.invoke(devices, ["pool", "info", "nope"])
    _no_crash(result)
    assert result.exit_code != 0
    assert "not found" in result.output


def test_pool_delete_cancelled(runner):
    result = runner.invoke(devices, ["pool", "delete", "p1"], input="n\n")
    _no_crash(result)
    assert result.exit_code == 0
    assert "Cancelled" in result.output


def test_pool_delete_forced(runner):
    result = runner.invoke(devices, ["pool", "delete", "p1", "--force"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Deleted pool 'p1'" in result.output
