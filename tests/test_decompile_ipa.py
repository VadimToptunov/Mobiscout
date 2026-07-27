"""Tests for framework.security.decompile.ipa.IPAAnalyzer.

Drives real parsing over a synthetic IPA (a zip with Payload/<App>.app holding a
real plist, a fake Mach-O binary carrying sensitive strings, and a Frameworks
dir). Guards: Info.plist parsing, binary string extraction, framework discovery,
jailbreak/cert-pinning detection, hash computation, and the missing-file path.
"""

import hashlib
import plistlib
import zipfile

import pytest

from framework.security.decompile.ipa import IPAAnalyzer
from framework.security.decompile.base import BinaryType, ProtectionType

PLIST = {
    "CFBundleIdentifier": "com.example.ios",
    "CFBundleShortVersionString": "3.4.1",
    "CFBundleExecutable": "MyApp",
    "CFBundleName": "MyApp",
    "MinimumOSVersion": "14.0",
}

BIN_STRINGS = [
    b"https://api.example.com/session",
    b"https://cydia.example.com/pkg",
    b"https://trustkit.example.com/pins",
]
BIN_CONTENT = b"\x00\x00".join(BIN_STRINGS)


def _build_ipa(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Payload/MyApp.app/Info.plist", plistlib.dumps(PLIST))
        zf.writestr("Payload/MyApp.app/MyApp", BIN_CONTENT)
        # framework dir marker (a file inside so the .framework dir materialises on extract)
        zf.writestr("Payload/MyApp.app/Frameworks/Alamofire.framework/Alamofire", b"bin")
    return path


@pytest.fixture()
def ipa(tmp_path):
    return _build_ipa(tmp_path / "app.ipa")


def test_analyze_parses_plist_metadata(ipa, tmp_path):
    result = IPAAnalyzer().analyze(ipa, output_dir=tmp_path / "out")
    assert result.binary_type == BinaryType.IPA
    assert result.package_name == "com.example.ios"
    assert result.version_name == "3.4.1"
    assert result.metadata["bundle_name"] == "MyApp"
    assert result.metadata["minimum_os"] == "14.0"


def test_analyze_extracts_strings_and_frameworks(ipa, tmp_path):
    result = IPAAnalyzer().analyze(ipa, output_dir=tmp_path / "out")
    values = {s.value for s in result.strings}
    assert "https://api.example.com/session" in values
    assert "Alamofire.framework" in result.native_libs


def test_analyze_detects_jailbreak_and_pinning(ipa, tmp_path):
    result = IPAAnalyzer().analyze(ipa, output_dir=tmp_path / "out")
    # 'cydia' inside the url string -> jailbreak; 'alamofire' -> cert pinning
    assert ProtectionType.JAILBREAK_DETECTION in result.protections
    assert ProtectionType.CERTIFICATE_PINNING in result.protections


def test_analyze_computes_hashes(ipa, tmp_path):
    result = IPAAnalyzer().analyze(ipa, output_dir=tmp_path / "out")
    raw = ipa.read_bytes()
    assert result.hashes["sha1"] == hashlib.sha1(raw).hexdigest()
    assert result.hashes["md5"] == hashlib.md5(raw).hexdigest()


def test_missing_ipa_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        IPAAnalyzer().analyze(tmp_path / "nope.ipa")


def test_parse_plist_happy_and_bad(tmp_path):
    analyzer = IPAAnalyzer()
    good = tmp_path / "Info.plist"
    good.write_bytes(plistlib.dumps({"CFBundleName": "X"}))
    assert analyzer._parse_plist(good) == {"CFBundleName": "X"}

    bad = tmp_path / "bad.plist"
    bad.write_bytes(b"not a plist at all")
    assert analyzer._parse_plist(bad) == {}


def test_analyze_without_payload_yields_no_app_metadata(tmp_path):
    """An IPA that lacks a Payload/*.app bundle must still produce a result with
    empty app-derived fields rather than crashing."""
    ipa = tmp_path / "empty.ipa"
    with zipfile.ZipFile(ipa, "w") as zf:
        zf.writestr("README.txt", "no payload here")
    result = IPAAnalyzer().analyze(ipa, output_dir=tmp_path / "out")
    assert result.package_name is None
    assert result.strings == []
    assert result.native_libs == []
