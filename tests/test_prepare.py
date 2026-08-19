"""Pre-crawl device preparation: opt-in permission grants + state reset, so a
system dialog can't stall the crawl. Commands are mocked — no device needed."""

import plistlib

import framework.devices.prepare as P


def test_android_keeps_dangerous_drops_normal():
    manifest = """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
      <uses-permission android:name="android.permission.CAMERA"/>
      <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
      <uses-permission android:name="android.permission.INTERNET"/>
    </manifest>"""
    assert P.android_permissions_from_manifest(manifest) == [
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.CAMERA",
    ]


def test_android_manifest_malformed_is_empty():
    assert P.android_permissions_from_manifest("<broken") == []


def test_ios_usage_keys_map_to_services_camera_has_none():
    plist = plistlib.dumps(
        {
            "NSPhotoLibraryUsageDescription": "x",
            "NSLocationWhenInUseUsageDescription": "x",
            "NSMicrophoneUsageDescription": "x",
            "NSCameraUsageDescription": "x",  # no simctl service -> dropped
        }
    )
    assert P.ios_privacy_services_from_plist(plist) == ["location", "microphone", "photos"]


def test_prepare_is_a_noop_without_flags():
    assert P.prepare_device({"platform": "ios", "udid": "x", "package": "y"}) == {
        "platform": "ios",
        "granted": [],
        "reset": False,
    }


def test_prepare_ios_resets_before_granting(monkeypatch):
    plist = plistlib.dumps({"NSPhotoLibraryUsageDescription": "x", "NSMicrophoneUsageDescription": "x"})
    monkeypatch.setattr(P, "_ios_app_plist", lambda config: plist)
    calls = []
    monkeypatch.setattr(P, "_run", lambda cmd: calls.append(cmd) or True)

    result = P.prepare_device(
        {"platform": "ios", "udid": "U1", "package": "com.acme", "grant_permissions": True, "reset_state": True}
    )
    assert result["reset"] is True
    assert result["granted"] == ["microphone", "photos"]
    # reset first, then a grant per service
    assert calls[0] == ["xcrun", "simctl", "privacy", "U1", "reset", "all", "com.acme"]
    assert ["xcrun", "simctl", "privacy", "U1", "grant", "photos", "com.acme"] in calls
    assert ["xcrun", "simctl", "privacy", "U1", "grant", "microphone", "com.acme"] in calls


def test_prepare_android_grants_each_dangerous_permission(monkeypatch):
    manifest = """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
      <uses-permission android:name="android.permission.CAMERA"/>
      <uses-permission android:name="android.permission.RECORD_AUDIO"/>
    </manifest>"""
    monkeypatch.setattr(P, "_android_manifest", lambda config: manifest)
    calls = []
    monkeypatch.setattr(P, "_run", lambda cmd: calls.append(cmd) or True)

    result = P.prepare_device(
        {"platform": "android", "udid": "emulator-5554", "package": "com.acme", "grant_permissions": True}
    )
    assert set(result["granted"]) == {"android.permission.CAMERA", "android.permission.RECORD_AUDIO"}
    assert ["adb", "-s", "emulator-5554", "shell", "pm", "grant", "com.acme", "android.permission.CAMERA"] in calls


def test_prepare_android_reset_uses_pm_clear(monkeypatch):
    calls = []
    monkeypatch.setattr(P, "_run", lambda cmd: calls.append(cmd) or True)
    result = P.prepare_device({"platform": "android", "udid": "s1", "package": "com.acme", "reset_state": True})
    assert result["reset"] is True
    assert calls == [["adb", "-s", "s1", "shell", "pm", "clear", "com.acme"]]
