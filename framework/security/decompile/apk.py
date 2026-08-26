"""Analyzer extracted from decompiler (mechanical split; see decompile/base.py)."""

import hashlib
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import xml.etree.ElementTree as ET

from framework.security import patterns
from framework.security.decompile.base import (
    ProtectionType,
    BinaryType,
    StringFinding,
    DecompileResult,
)


class APKDecompiler:
    """
    APK Decompilation and Analysis

    Decompiles Android APK files and extracts security-relevant information.
    """

    # Sensitive string patterns (canonical set; see framework/security/patterns.py)
    SENSITIVE_PATTERNS = patterns.DECOMPILE_SENSITIVE_PATTERNS

    # Binary (aapt-compiled) AndroidManifest.xml magic: chunk type 0x0003 followed
    # by header size 0x0008, i.e. 0x00080003 little-endian.
    AXML_MAGIC = b"\x03\x00\x08\x00"

    # Root detection indicators. The bare "su" token that used to head this list
    # matched inside "subscriptions"/"issuer"/"support", so only qualified forms
    # are listed; matching is token-bounded, see _has_indicator.
    ROOT_INDICATORS = [
        "/system/app/Superuser",
        "/system/xbin/su",
        "/system/bin/su",
        "/sbin/su",
        "com.noshufou.android.su",
        "com.thirdparty.superuser",
        "eu.chainfire.supersu",
        "com.koushikdutta.superuser",
        "com.topjohnwu.magisk",
        "RootBeer",
        "RootTools",
        "isRooted",
        "checkRoot",
        "detectRoot",
    ]

    # Emulator detection indicators
    EMULATOR_INDICATORS = [
        "generic",
        "goldfish",
        "vbox",
        "genymotion",
        "sdk_google_phone",
        "google_sdk",
        "Andy",
        "Emulator",
        "BlueStacks",
        "Nox",
        "isEmulator",
    ]

    # Debug detection indicators
    DEBUG_INDICATORS = ["isDebuggerConnected", "Debug.isDebuggerConnected", "Debugger", "JDWP", "waitForDebugger"]

    # Obfuscation indicators
    OBFUSCATION_INDICATORS = ["proguard", "dexguard", "allatori", "zelix", "stringer", "dasho", "arxan"]

    def decompile(self, apk_path: Path, output_dir: Optional[Path] = None) -> DecompileResult:
        """Decompile APK and extract information"""
        if not apk_path.exists():
            raise FileNotFoundError(f"APK not found: {apk_path}")

        # Create output directory
        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="apk_decompile_"))
        else:
            output_dir.mkdir(parents=True, exist_ok=True)

        # Calculate hashes
        hashes = self._calculate_hashes(apk_path)

        # Extract APK contents
        extract_dir = output_dir / "extracted"
        with zipfile.ZipFile(apk_path, "r") as zf:
            zf.extractall(extract_dir)

        # Try to decompile with apktool if available. It runs first because it is
        # the only thing here that can decode a binary manifest, and the zip entry
        # is compiled AXML in every shipped APK.
        apktool_dir = output_dir / "apktool"
        apktool_ok = self._run_apktool(apk_path, apktool_dir)

        # Parse AndroidManifest
        manifest_info = self._parse_manifest(extract_dir / "AndroidManifest.xml")
        if not manifest_info["parsed"] and apktool_ok:
            manifest_info = self._parse_manifest(apktool_dir / "AndroidManifest.xml")

        # Extract strings from DEX files
        strings = self._extract_strings(extract_dir)

        # Find native libraries
        native_libs = self._find_native_libs(extract_dir)

        # Detect protections
        protections = self._detect_protections(extract_dir, strings)

        # Try to decompile with jadx if available
        self._run_jadx(apk_path, output_dir / "jadx")

        return DecompileResult(
            binary_type=BinaryType.APK,
            binary_path=str(apk_path),
            output_dir=str(output_dir),
            package_name=manifest_info.get("package"),
            version_name=manifest_info.get("version_name"),
            version_code=manifest_info.get("version_code"),
            min_sdk=manifest_info.get("min_sdk"),
            target_sdk=manifest_info.get("target_sdk"),
            permissions=manifest_info.get("permissions", []),
            activities=manifest_info.get("activities", []),
            services=manifest_info.get("services", []),
            receivers=manifest_info.get("receivers", []),
            providers=manifest_info.get("providers", []),
            native_libs=native_libs,
            strings=strings,
            protections=protections,
            hashes=hashes,
            metadata={
                "file_size": apk_path.stat().st_size,
                "signing_info": self._get_signing_info(apk_path),
                # Carried so consumers can tell "no dangerous permissions, nothing
                # exported" from "the manifest was never read".
                "manifest_parsed": manifest_info["parsed"],
                "manifest_error": manifest_info["unparsed_reason"],
            },
        )

    def _calculate_hashes(self, file_path: Path) -> Dict[str, str]:
        """Calculate file hashes"""
        hashes = {}
        content = file_path.read_bytes()

        hashes["md5"] = hashlib.md5(content).hexdigest()
        hashes["sha1"] = hashlib.sha1(content).hexdigest()
        hashes["sha256"] = hashlib.sha256(content).hexdigest()

        return hashes

    def _parse_manifest(self, manifest_path: Path) -> Dict[str, Any]:
        """Parse AndroidManifest.xml.

        ``parsed`` reports whether the manifest was actually read: an unparsed
        manifest yields the same empty component lists as a manifest that declares
        nothing, and callers must not confuse the two.
        """
        info: Dict[str, Any] = {
            "permissions": [],
            "activities": [],
            "services": [],
            "receivers": [],
            "providers": [],
            "parsed": False,
            "unparsed_reason": None,
        }

        try:
            raw = manifest_path.read_bytes()
        except OSError as e:
            info["unparsed_reason"] = f"AndroidManifest.xml could not be read: {e}"
            return info

        if raw[:4] == self.AXML_MAGIC:
            # There is no AXML decoder here, so report the gap instead of returning
            # an empty manifest that reads as "clean".
            info["unparsed_reason"] = "AndroidManifest.xml is binary AXML; install apktool to decode it"
            return info

        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            info["unparsed_reason"] = f"AndroidManifest.xml is not parseable XML: {e}"
            return info

        # Package info
        info["package"] = root.get("package")
        info["version_name"] = root.get("{http://schemas.android.com/apk/res/android}versionName")
        version_code = root.get("{http://schemas.android.com/apk/res/android}versionCode")
        info["version_code"] = int(version_code) if version_code else None

        # SDK versions
        uses_sdk = root.find(".//uses-sdk")
        if uses_sdk is not None:
            min_sdk = uses_sdk.get("{http://schemas.android.com/apk/res/android}minSdkVersion")
            target_sdk = uses_sdk.get("{http://schemas.android.com/apk/res/android}targetSdkVersion")
            info["min_sdk"] = int(min_sdk) if min_sdk else None
            info["target_sdk"] = int(target_sdk) if target_sdk else None

        # Permissions
        for perm in root.findall(".//uses-permission"):
            perm_name = perm.get("{http://schemas.android.com/apk/res/android}name")
            if perm_name:
                info["permissions"].append(perm_name)

        # Components
        for activity in root.findall(".//activity"):
            name = activity.get("{http://schemas.android.com/apk/res/android}name")
            if name:
                info["activities"].append(name)

        for service in root.findall(".//service"):
            name = service.get("{http://schemas.android.com/apk/res/android}name")
            if name:
                info["services"].append(name)

        for receiver in root.findall(".//receiver"):
            name = receiver.get("{http://schemas.android.com/apk/res/android}name")
            if name:
                info["receivers"].append(name)

        for provider in root.findall(".//provider"):
            name = provider.get("{http://schemas.android.com/apk/res/android}name")
            if name:
                info["providers"].append(name)

        info["parsed"] = True
        return info

    def _extract_strings(self, extract_dir: Path) -> List[StringFinding]:
        """Extract strings from DEX files"""
        strings = []

        # Find all DEX files
        dex_files = list(extract_dir.glob("*.dex"))

        for dex_file in dex_files:
            dex_strings = self._extract_dex_strings(dex_file)
            strings.extend(dex_strings)

        # Also search resource files
        res_dir = extract_dir / "res"
        if res_dir.exists():
            for xml_file in res_dir.rglob("*.xml"):
                try:
                    content = xml_file.read_text(encoding="utf-8", errors="ignore")
                    for category, pattern in self.SENSITIVE_PATTERNS.items():
                        for match in re.finditer(pattern, content, re.IGNORECASE):
                            strings.append(
                                StringFinding(
                                    value=match.group(0),
                                    location=str(xml_file),
                                    category=category,
                                    confidence=0.7,
                                )
                            )
                except (OSError, UnicodeDecodeError):
                    pass

        return strings

    def _extract_dex_strings(self, dex_path: Path) -> List[StringFinding]:
        """Extract strings from a DEX file"""
        strings = []

        try:
            # Simple string extraction using strings-like approach
            content = dex_path.read_bytes()

            # Extract ASCII strings
            ascii_strings = re.findall(rb"[\x20-\x7e]{4,}", content)

            for s in ascii_strings:
                try:
                    decoded = s.decode("utf-8")
                    for category, pattern in self.SENSITIVE_PATTERNS.items():
                        if re.search(pattern, decoded, re.IGNORECASE):
                            strings.append(
                                StringFinding(
                                    value=decoded,
                                    location=str(dex_path),
                                    category=category,
                                    confidence=0.8,
                                )
                            )
                            break
                except UnicodeDecodeError:
                    pass

        except OSError:
            pass

        return strings

    def _find_native_libs(self, extract_dir: Path) -> List[str]:
        """Find native libraries"""
        libs = []

        lib_dir = extract_dir / "lib"
        if lib_dir.exists():
            for so_file in lib_dir.rglob("*.so"):
                # APK entry paths are always '/'-separated; use as_posix() so the
                # result is identical on Windows (where relative_to would yield '\\').
                libs.append(so_file.relative_to(extract_dir).as_posix())

        return libs

    def _detect_protections(self, extract_dir: Path, strings: List[StringFinding]) -> List[ProtectionType]:
        """Detect binary protections"""
        protections = []

        # Get all string values for detection
        all_strings = {s.value.lower() for s in strings}

        # Check root detection
        if self._has_indicator(all_strings, self.ROOT_INDICATORS):
            protections.append(ProtectionType.ROOT_DETECTION)

        # Check emulator detection
        if self._has_indicator(all_strings, self.EMULATOR_INDICATORS):
            protections.append(ProtectionType.EMULATOR_DETECTION)

        # Check debug detection
        if self._has_indicator(all_strings, self.DEBUG_INDICATORS):
            protections.append(ProtectionType.DEBUG_DETECTION)

        # Check obfuscation
        if self._has_indicator(all_strings, self.OBFUSCATION_INDICATORS):
            protections.append(ProtectionType.OBFUSCATION)

        # Check for certificate pinning
        pinning_indicators = ["certificatepinner", "okhttp3.certificatepinner", "trustmanager"]
        if self._has_indicator(all_strings, pinning_indicators):
            protections.append(ProtectionType.CERTIFICATE_PINNING)

        return protections

    @staticmethod
    def _has_indicator(strings: Set[str], indicators: List[str]) -> bool:
        """Whether any indicator occurs as a whole token in one of the strings.

        A plain substring test claimed protections from noise — "su" matched inside
        "subscriptions", "Nox" inside "noxious" — and a fabricated detection also
        hides the real gap, because "Missing Protection: X" is only reported when X
        is absent. Boundaries are applied on the alphanumeric ends of an indicator,
        so path forms like "/system/xbin/su" still match inside a longer path.
        """
        for indicator in indicators:
            token = indicator.lower()
            prefix = r"(?<![0-9a-z])" if token[:1].isalnum() else ""
            suffix = r"(?![0-9a-z])" if token[-1:].isalnum() else ""
            pattern = re.compile(prefix + re.escape(token) + suffix)
            if any(pattern.search(s) for s in strings):
                return True

        return False

    def _get_signing_info(self, apk_path: Path) -> Dict[str, Any]:
        """Get APK signing information"""
        info: Dict[str, Any] = {}

        try:
            # Try using apksigner if available
            result = subprocess.run(
                ["apksigner", "verify", "--print-certs", str(apk_path)], capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                info["signed"] = True
                info["details"] = result.stdout
            else:
                info["signed"] = False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            info["signed"] = "unknown"

        return info

    def _run_apktool(self, apk_path: Path, output_dir: Path) -> bool:
        """Run apktool for decompilation"""
        try:
            result = subprocess.run(
                ["apktool", "d", "-f", "-o", str(output_dir), str(apk_path)], capture_output=True, timeout=300
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _run_jadx(self, apk_path: Path, output_dir: Path) -> bool:
        """Run jadx for Java decompilation"""
        try:
            result = subprocess.run(["jadx", "-d", str(output_dir), str(apk_path)], capture_output=True, timeout=600)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False
