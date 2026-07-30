"""DeviceManager parses adb/simctl output into a uniform device list. It shells
out, so tests drive it through a mocked subprocess.run — no real device needed.
This is what the daemon's device/list handler depends on, and it had no tests."""

import json
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

from framework.devices.device_manager import DeviceManager

_ADB_DEVICES = "List of devices attached\n" "emulator-5554   device product:sdk_gphone64\n" "R5-OFF          offline\n"

_SIMCTL = json.dumps(
    {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-18-2": [
                {"udid": "AAA", "name": "iPhone 16", "state": "Booted", "isAvailable": True},
                {"udid": "BBB", "name": "iPad", "state": "Shutdown", "isAvailable": False},
            ]
        }
    }
)


def _fake_run(returncode=0):
    """A subprocess.run stand-in that answers by inspecting the command."""

    def run(cmd, *a, **k):
        if cmd[:3] == ["adb", "devices", "-l"]:
            return SimpleNamespace(returncode=returncode, stdout=_ADB_DEVICES)
        if "ro.product.model" in cmd:
            return SimpleNamespace(returncode=0, stdout="Pixel 8\n")
        if "ro.build.version.sdk" in cmd:
            return SimpleNamespace(returncode=0, stdout="34\n")
        if "simctl" in cmd:
            return SimpleNamespace(returncode=returncode, stdout=_SIMCTL)
        return SimpleNamespace(returncode=1, stdout="")

    return run


@pytest.fixture()
def patched_run():
    with mock.patch("framework.devices.device_manager.subprocess.run", side_effect=_fake_run()) as m:
        yield m


def test_list_android_devices_parses_and_enriches(patched_run):
    devices = DeviceManager.list_android_devices()
    ids = {d["id"]: d for d in devices}
    assert set(ids) == {"emulator-5554", "R5-OFF"}
    online = ids["emulator-5554"]
    assert online["status"] == "online" and online["name"] == "Pixel 8" and online["api_level"] == 34
    assert ids["R5-OFF"]["status"] == "offline"  # non-"device" status passed through


def test_list_android_devices_empty_when_adb_absent():
    with mock.patch("framework.devices.device_manager.subprocess.run", side_effect=FileNotFoundError):
        assert DeviceManager.list_android_devices() == []


def test_android_name_and_api_fall_back_on_error():
    def flaky(cmd, *a, **k):
        if cmd[:3] == ["adb", "devices", "-l"]:
            return SimpleNamespace(returncode=0, stdout="List\nDEV device\n")
        if "ro.product.model" in cmd:
            return SimpleNamespace(returncode=0, stdout="\n")  # empty -> fall back to id
        raise subprocess.TimeoutExpired(cmd, 2)  # api level lookup times out -> None

    with mock.patch("framework.devices.device_manager.subprocess.run", side_effect=flaky):
        dev = DeviceManager.list_android_devices()[0]
    assert dev["name"] == "DEV" and dev["api_level"] is None


def test_list_ios_simulators_only_available(patched_run):
    devices = DeviceManager.list_ios_simulators()
    assert len(devices) == 1  # unavailable iPad excluded
    d = devices[0]
    assert d["id"] == "AAA" and d["platform"] == "ios" and d["status"] == "booted"


def test_list_ios_handles_bad_json():
    with mock.patch(
        "framework.devices.device_manager.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="not json"),
    ):
        assert DeviceManager.list_ios_simulators() == []


def test_list_all_respects_platform_filter(patched_run):
    assert {d["platform"] for d in DeviceManager.list_all_devices("android")} == {"android"}
    assert {d["platform"] for d in DeviceManager.list_all_devices("ios")} == {"ios"}
    assert {d["platform"] for d in DeviceManager.list_all_devices("all")} == {"android", "ios"}


def test_get_device_and_health(patched_run):
    assert DeviceManager.get_device("AAA")["name"] == "iPhone 16"
    assert DeviceManager.get_device("missing") is None

    healthy = DeviceManager.check_device_health("emulator-5554")
    assert healthy["healthy"] is True and healthy["platform"] == "android"
    assert DeviceManager.check_device_health("R5-OFF")["healthy"] is False
    assert DeviceManager.check_device_health("missing") == {"healthy": False, "error": "Device not found"}


def test_get_available_devices_filters_online(patched_run):
    available = DeviceManager.get_available_devices()
    statuses = {d["status"] for d in available}
    assert statuses <= {"online", "booted"} and "offline" not in statuses
    # emulator (online) + iPhone (booted) are available; the offline one is not.
    assert {d["id"] for d in available} == {"emulator-5554", "AAA"}


def test_aliases_delegate(patched_run):
    # list_ios_devices / get_all_devices are thin aliases of the real methods.
    assert DeviceManager.list_ios_devices() == DeviceManager.list_ios_simulators()
    assert DeviceManager.get_all_devices() == DeviceManager.list_all_devices()


def test_android_name_falls_back_on_oserror():
    def run(cmd, *a, **k):
        if cmd[:3] == ["adb", "devices", "-l"]:
            return SimpleNamespace(returncode=0, stdout="List\nDEV device\n")
        raise OSError("adb exploded")  # name + api lookups both raise

    with mock.patch("framework.devices.device_manager.subprocess.run", side_effect=run):
        dev = DeviceManager.list_android_devices()[0]
    assert dev["name"] == "DEV" and dev["api_level"] is None


# ---- install / uninstall (mocked subprocess; path existence patched) ----


def _ok(stdout="Success"):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def test_install_app_android_builds_adb_argv(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_text("x")
    with mock.patch("framework.devices.device_manager.subprocess.run", return_value=_ok()) as run:
        res = DeviceManager.install_app("android", "emulator-5554", str(apk))
    assert res["ok"] is True and res["detail"] == "installed"
    assert run.call_args[0][0] == ["adb", "-s", "emulator-5554", "install", "-r", str(apk)]


def test_install_app_ios_builds_simctl_argv(tmp_path):
    app = tmp_path / "App.app"
    app.mkdir()
    with mock.patch("framework.devices.device_manager.subprocess.run", return_value=_ok()) as run:
        res = DeviceManager.install_app("ios", "AAA", str(app))
    assert res["ok"] is True
    assert run.call_args[0][0] == ["xcrun", "simctl", "install", "AAA", str(app)]


def test_install_app_ios_defaults_to_booted(tmp_path):
    app = tmp_path / "App.app"
    app.mkdir()
    with mock.patch("framework.devices.device_manager.subprocess.run", return_value=_ok()) as run:
        DeviceManager.install_app("ios", "", str(app))
    assert run.call_args[0][0] == ["xcrun", "simctl", "install", "booted", str(app)]


def test_install_app_missing_path_fails_without_shelling_out():
    with mock.patch("framework.devices.device_manager.subprocess.run") as run:
        res = DeviceManager.install_app("android", "emulator-5554", "/no/such/app.apk")
    assert res["ok"] is False and "does not exist" in res["detail"]
    run.assert_not_called()


def test_install_app_nonzero_exit_is_failure(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_text("x")
    fail = SimpleNamespace(returncode=1, stdout="", stderr="adb: device offline")
    with mock.patch("framework.devices.device_manager.subprocess.run", return_value=fail):
        res = DeviceManager.install_app("android", "emulator-5554", str(apk))
    assert res["ok"] is False and "offline" in res["detail"]


def test_install_app_adb_exit0_failure_stdout_is_failure(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_text("x")
    # adb returns 0 but prints a Failure line — must be treated as a failure.
    bad = SimpleNamespace(returncode=0, stdout="Failure [INSTALL_FAILED_OLDER_SDK]", stderr="")
    with mock.patch("framework.devices.device_manager.subprocess.run", return_value=bad):
        res = DeviceManager.install_app("android", "emulator-5554", str(apk))
    assert res["ok"] is False and "INSTALL_FAILED_OLDER_SDK" in res["detail"]


def test_install_app_never_raises(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_text("x")
    with mock.patch("framework.devices.device_manager.subprocess.run", side_effect=FileNotFoundError("adb")):
        res = DeviceManager.install_app("android", "emulator-5554", str(apk))
    assert res["ok"] is False


def test_uninstall_app_android_builds_adb_argv():
    with mock.patch("framework.devices.device_manager.subprocess.run", return_value=_ok()) as run:
        res = DeviceManager.uninstall_app("android", "emulator-5554", "com.x")
    assert res["ok"] is True and res["detail"] == "uninstalled"
    assert run.call_args[0][0] == ["adb", "-s", "emulator-5554", "uninstall", "com.x"]


def test_uninstall_app_ios_builds_simctl_argv():
    with mock.patch("framework.devices.device_manager.subprocess.run", return_value=_ok()) as run:
        res = DeviceManager.uninstall_app("ios", "", "com.x.bundle")
    assert res["ok"] is True
    assert run.call_args[0][0] == ["xcrun", "simctl", "uninstall", "booted", "com.x.bundle"]


def test_uninstall_app_adb_exit0_failure_stdout_is_failure():
    bad = SimpleNamespace(returncode=0, stdout="Failure [DELETE_FAILED_INTERNAL_ERROR]", stderr="")
    with mock.patch("framework.devices.device_manager.subprocess.run", return_value=bad):
        res = DeviceManager.uninstall_app("android", "emulator-5554", "com.x")
    assert res["ok"] is False and "DELETE_FAILED_INTERNAL_ERROR" in res["detail"]


def test_uninstall_app_never_raises():
    with mock.patch("framework.devices.device_manager.subprocess.run", side_effect=OSError("boom")):
        res = DeviceManager.uninstall_app("android", "emulator-5554", "com.x")
    assert res["ok"] is False
