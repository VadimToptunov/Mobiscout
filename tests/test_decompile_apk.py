"""Tests for framework.security.decompile.apk.APKDecompiler.

These drive real parsing/orchestration over a synthetic APK (a zip built in the
test with a text AndroidManifest, a fake classes.dex carrying sensitive strings,
a native .so and a res xml). External decompiler binaries (apktool/jadx/
apksigner) are stubbed out via subprocess so only the module's own extraction and
protection-detection logic is exercised. Guards: manifest parsing, hash
computation, DEX/resource string finding, native-lib discovery, protection
detection, and the missing-file error path.
"""

import hashlib
import subprocess
import zipfile

import pytest

from framework.security.decompile.apk import APKDecompiler
from framework.security.decompile.base import BinaryType, ProtectionType

MANIFEST = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
    'package="com.example.app" android:versionName="1.2.3" android:versionCode="42">\n'
    '  <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="33"/>\n'
    '  <uses-permission android:name="android.permission.INTERNET"/>\n'
    "  <application>\n"
    '    <activity android:name=".MainActivity"/>\n'
    '    <service android:name=".SyncService"/>\n'
    '    <receiver android:name=".BootReceiver"/>\n'
    '    <provider android:name=".DataProvider"/>\n'
    "  </application>\n"
    "</manifest>\n"
)

# ASCII runs separated by NUL so each becomes its own StringFinding. Each run both
# matches a SENSITIVE_PATTERN (url/aws_key) and carries a protection indicator.
DEX_STRINGS = [
    b"https://api.example.com/v1/login",
    b"AKIAABCDEFGHIJKLMNOP",
    b"https://host.example.com/eu.chainfire.supersu",
    b"https://host.example.com/isDebuggerConnected",
    b"https://okhttp3.certificatepinner.example.com",
    b"https://host.example.com/goldfish-emulator",
]
DEX_CONTENT = b"\x00\x00".join(DEX_STRINGS)


def _build_apk(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("AndroidManifest.xml", MANIFEST)
        zf.writestr("classes.dex", DEX_CONTENT)
        zf.writestr("lib/arm64-v8a/libnative.so", b"\x7fELF payload")
        zf.writestr(
            "res/values/strings.xml", '<resources><string name="u">https://res.example.com</string></resources>'
        )
    return path


@pytest.fixture()
def apk(tmp_path):
    return _build_apk(tmp_path / "app.apk")


@pytest.fixture(autouse=True)
def _stub_external_tools(monkeypatch):
    """apktool/jadx/apksigner are not installed in CI; make every subprocess call
    behave as tool-not-found so we test only in-process logic."""

    def _not_found(*args, **kwargs):
        raise FileNotFoundError("external tool not available")

    monkeypatch.setattr(subprocess, "run", _not_found)


def test_decompile_parses_manifest(apk, tmp_path):
    result = APKDecompiler().decompile(apk, output_dir=tmp_path / "out")
    assert result.binary_type == BinaryType.APK
    assert result.package_name == "com.example.app"
    assert result.version_name == "1.2.3"
    assert result.version_code == 42
    assert result.min_sdk == 21
    assert result.target_sdk == 33
    assert "android.permission.INTERNET" in result.permissions
    assert ".MainActivity" in result.activities
    assert ".SyncService" in result.services
    assert ".BootReceiver" in result.receivers
    assert ".DataProvider" in result.providers


def test_decompile_computes_hashes_and_size(apk, tmp_path):
    result = APKDecompiler().decompile(apk, output_dir=tmp_path / "out")
    raw = apk.read_bytes()
    assert result.hashes["md5"] == hashlib.md5(raw).hexdigest()
    assert result.hashes["sha256"] == hashlib.sha256(raw).hexdigest()
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert result.size_bytes == apk.stat().st_size


def test_decompile_finds_native_libs_and_strings(apk, tmp_path):
    result = APKDecompiler().decompile(apk, output_dir=tmp_path / "out")
    assert "lib/arm64-v8a/libnative.so" in result.native_libs

    values = {s.value for s in result.strings}
    assert "https://api.example.com/v1/login" in values
    assert "AKIAABCDEFGHIJKLMNOP" in values
    # resource xml URL captured too
    assert any("res.example.com" in v for v in values)
    categories = {s.category for s in result.strings}
    assert "url" in categories and "aws_key" in categories


def test_decompile_detects_protections(apk, tmp_path):
    result = APKDecompiler().decompile(apk, output_dir=tmp_path / "out")
    assert ProtectionType.ROOT_DETECTION in result.protections
    assert ProtectionType.DEBUG_DETECTION in result.protections
    assert ProtectionType.EMULATOR_DETECTION in result.protections
    assert ProtectionType.CERTIFICATE_PINNING in result.protections


def test_signing_info_unknown_when_tool_absent(apk, tmp_path):
    result = APKDecompiler().decompile(apk, output_dir=tmp_path / "out")
    assert result.metadata["signing_info"]["signed"] == "unknown"


def test_missing_apk_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        APKDecompiler().decompile(tmp_path / "does_not_exist.apk")


def test_binary_manifest_parses_to_empty_info(tmp_path):
    """A binary (aapt-compiled) AndroidManifest can't be parsed as text XML; the
    parser must degrade to empty metadata rather than raise."""
    dec = APKDecompiler()
    manifest = tmp_path / "AndroidManifest.xml"
    manifest.write_bytes(b"\x03\x00\x08\x00binary-xml-not-text")
    info = dec._parse_manifest(manifest)
    assert info["permissions"] == []
    assert info["activities"] == []
    assert info.get("package") is None


def test_to_dict_is_json_shaped(apk, tmp_path):
    import json

    result = APKDecompiler().decompile(apk, output_dir=tmp_path / "out")
    d = result.to_dict()
    assert d["binary_type"] == "apk"
    assert d["package_name"] == "com.example.app"
    # protections rendered as full catalogue of {name, detected, ...}
    detected = {p["name"] for p in d["protections"] if p["detected"]}
    assert "Root Detection" in detected
    json.loads(json.dumps(d))  # serialisable
