"""Android SDK PATH resolution — the fix for a GUI-launched engine getting a minimal
PATH (no adb/emulator), which made Android devices/AVDs silently invisible while iOS
worked. Device-free: uses a fake SDK dir and a controlled PATH."""

import os

import pytest

import framework.devices.android_sdk as sdk


@pytest.fixture(autouse=True)
def _isolate_common_bins(monkeypatch):
    # Don't let the test box's real /opt/homebrew etc. leak into PATH assertions.
    monkeypatch.setattr(sdk, "_COMMON_BIN_DIRS", ())


def _fake_sdk(tmp_path):
    root = tmp_path / "sdk"
    (root / "platform-tools").mkdir(parents=True)
    (root / "emulator").mkdir(parents=True)
    return root


def test_resolves_from_env_and_prepends_tool_dirs(tmp_path, monkeypatch):
    root = _fake_sdk(tmp_path)
    monkeypatch.setenv("ANDROID_HOME", str(root))
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/bin"]))

    sdk.ensure_tooling_on_path()

    parts = os.environ["PATH"].split(os.pathsep)
    assert str(root / "platform-tools") in parts  # adb now findable
    assert str(root / "emulator") in parts  # emulator now findable
    # prepended, so the SDK's tools win over anything else
    assert parts.index(str(root / "platform-tools")) < parts.index("/usr/bin")


def test_falls_back_to_default_location_when_env_unset(tmp_path, monkeypatch):
    # No env vars: resolve from the per-OS default (~/Library/Android/sdk on macOS).
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    home = tmp_path / "home"
    (home / "Library" / "Android" / "sdk" / "platform-tools").mkdir(parents=True)
    monkeypatch.setattr(sdk.Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("PATH", "/usr/bin")

    sdk.ensure_tooling_on_path()

    assert str(home / "Library" / "Android" / "sdk" / "platform-tools") in os.environ["PATH"].split(os.pathsep)
    assert os.environ["ANDROID_HOME"] == str(home / "Library" / "Android" / "sdk")  # exported when it was unset


def test_idempotent_no_duplicate_entries(tmp_path, monkeypatch):
    root = _fake_sdk(tmp_path)
    monkeypatch.setenv("ANDROID_HOME", str(root))
    monkeypatch.setenv("PATH", "/usr/bin")

    sdk.ensure_tooling_on_path()
    once = os.environ["PATH"]
    sdk.ensure_tooling_on_path()
    assert os.environ["PATH"] == once  # second call adds nothing


def test_noop_when_no_sdk_found(tmp_path, monkeypatch):
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(sdk.Path, "home", staticmethod(lambda: tmp_path / "empty"))
    monkeypatch.setenv("PATH", "/usr/bin")

    sdk.ensure_tooling_on_path()

    assert sdk.sdk_root() is None
    assert os.environ["PATH"] == "/usr/bin"  # untouched (common bins isolated off)
