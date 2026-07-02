"""Analyzer extracted from decompiler (mechanical split; see decompile/base.py)."""

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET

from framework.security.decompile.base import (
    ProtectionType,
    BinaryType,
    StringFinding,
    ProtectionInfo,
    NativeLibInfo,
    SecurityFinding,
    DecompileResult,
)


class APKDecompiler:
    """
    APK Decompilation and Analysis

    Decompiles Android APK files and extracts security-relevant information.
    """

    # Sensitive string patterns
    SENSITIVE_PATTERNS = {
        "url": r'https?://[^\s"\'<>]+',
        "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "api_key": r'(?:api[_-]?key|apikey|api_secret)["\s:=]+["\']?([\w\-]{20,})["\']?',
        "aws_key": r"AKIA[0-9A-Z]{16}",
        "google_api": r"AIza[0-9A-Za-z\-_]{35}",
        "firebase": r"[a-z0-9-]+\.firebaseio\.com",
        "password": r'(?:password|passwd|pwd)["\s:=]+["\']?([^\s"\']{4,})["\']?',
        "private_key": r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
        "jwt": r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+",
        "sql_query": r"(?:SELECT|INSERT|UPDATE|DELETE)\s+.+\s+(?:FROM|INTO|SET)",
    }

    # Root detection indicators
    ROOT_INDICATORS = [
        "su",
        "/system/app/Superuser",
        "/system/xbin/su",
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

        # Parse AndroidManifest
        manifest_info = self._parse_manifest(extract_dir / "AndroidManifest.xml")

        # Extract strings from DEX files
        strings = self._extract_strings(extract_dir)

        # Find native libraries
        native_libs = self._find_native_libs(extract_dir)

        # Detect protections
        protections = self._detect_protections(extract_dir, strings)

        # Try to decompile with apktool if available
        self._run_apktool(apk_path, output_dir / "apktool")

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
        """Parse AndroidManifest.xml"""
        info: Dict[str, Any] = {
            "permissions": [],
            "activities": [],
            "services": [],
            "receivers": [],
            "providers": [],
        }

        try:
            # Try parsing as binary XML first
            # If that fails, try as text XML
            try:
                tree = ET.parse(manifest_path)
                root = tree.getroot()
            except ET.ParseError:
                # Binary XML - would need axml parser
                return info

            ns = {"android": "http://schemas.android.com/apk/res/android"}

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

        except (OSError, ET.ParseError):
            pass

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
                    content = xml_file.read_text(errors="ignore")
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
                libs.append(str(so_file.relative_to(extract_dir)))

        return libs

    def _detect_protections(self, extract_dir: Path, strings: List[StringFinding]) -> List[ProtectionType]:
        """Detect binary protections"""
        protections = []

        # Get all string values for detection
        all_strings = {s.value.lower() for s in strings}

        # Check root detection
        if any(indicator.lower() in s for s in all_strings for indicator in self.ROOT_INDICATORS):
            protections.append(ProtectionType.ROOT_DETECTION)

        # Check emulator detection
        if any(indicator.lower() in s for s in all_strings for indicator in self.EMULATOR_INDICATORS):
            protections.append(ProtectionType.EMULATOR_DETECTION)

        # Check debug detection
        if any(indicator.lower() in s for s in all_strings for indicator in self.DEBUG_INDICATORS):
            protections.append(ProtectionType.DEBUG_DETECTION)

        # Check obfuscation
        if any(indicator.lower() in s for s in all_strings for indicator in self.OBFUSCATION_INDICATORS):
            protections.append(ProtectionType.OBFUSCATION)

        # Check for certificate pinning
        pinning_indicators = ["certificatepinner", "okhttp3.certificatepinner", "trustmanager"]
        if any(indicator in s for s in all_strings for indicator in pinning_indicators):
            protections.append(ProtectionType.CERTIFICATE_PINNING)

        return protections

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
