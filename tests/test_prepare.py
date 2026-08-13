"""Opt-in device prep (device-free): the adb/simctl command builders."""

from framework.devices.prepare import (
    android_prepare_commands,
    ios_prepare_commands,
    prepare_commands,
)

PKG = "com.example.app"


def test_android_grant_only_by_default():
    cmds = android_prepare_commands(PKG, serial="emulator-5554", grant=True, reset=False)
    assert all(c[:3] == ["adb", "-s", "emulator-5554"] for c in cmds)
    assert all("grant" in c for c in cmds)
    assert not any("clear" in c for c in cmds)  # reset off -> no pm clear


def test_android_reset_runs_before_grants():
    cmds = android_prepare_commands(PKG, grant=True, reset=True, permissions=["android.permission.CAMERA"])
    assert cmds[0] == ["adb", "shell", "pm", "clear", PKG]  # reset first, so grants survive it
    assert cmds[1] == ["adb", "shell", "pm", "grant", PKG, "android.permission.CAMERA"]


def test_ios_privacy_grants():
    cmds = ios_prepare_commands("com.example.app", udid=None, grant=True, reset=True, services=["camera"])
    assert cmds[0] == ["xcrun", "simctl", "privacy", "booted", "reset", "all", "com.example.app"]
    assert cmds[1] == ["xcrun", "simctl", "privacy", "booted", "grant", "camera", "com.example.app"]


def test_prepare_commands_dispatches_on_platform():
    android = prepare_commands({"package": PKG, "platform": "android", "prepare": {"grant": True}})
    assert android and android[0][0] == "adb"
    ios = prepare_commands({"package": PKG, "platform": "ios", "udid": "UDID", "prepare": {"reset": True, "grant": False}})
    assert ios == [["xcrun", "simctl", "privacy", "UDID", "reset", "all", PKG]]


def test_no_prepare_block_is_noop():
    assert prepare_commands({"package": PKG, "platform": "android"}) == []
