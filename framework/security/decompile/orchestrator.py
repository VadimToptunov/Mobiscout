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

from framework.security.decompile.apk import APKDecompiler
from framework.security.decompile.ipa import IPAAnalyzer
from framework.security.decompile.native import NativeLibAnalyzer


class Decompiler:
    """
    Comprehensive Decompiler

    Combines all decompilation and analysis capabilities.
    """

    def __init__(self):
        self.apk_decompiler = APKDecompiler()
        self.ipa_analyzer = IPAAnalyzer()
        self.native_analyzer = NativeLibAnalyzer()

    def analyze(self, binary_path: Path, output_dir: Optional[Path] = None) -> DecompileResult:
        """Analyze any supported binary"""
        suffix = binary_path.suffix.lower()

        if suffix == ".apk":
            return self.apk_decompiler.decompile(binary_path, output_dir)
        elif suffix == ".ipa":
            return self.ipa_analyzer.analyze(binary_path, output_dir)
        else:
            raise ValueError(f"Unsupported binary type: {suffix}")

    def decompile(
        self,
        binary_path: Path,
        output_dir: Optional[Path] = None,
        extract_strings: bool = True,
        analyze_native: bool = True,
    ) -> DecompileResult:
        """
        Decompile binary with options.

        CLI-compatible entry point.
        """
        result = self.analyze(binary_path, output_dir)

        # Add security findings based on analysis
        result.security_findings = self._generate_security_findings(result)

        return result

    def _generate_security_findings(self, result: DecompileResult) -> List[SecurityFinding]:
        """Generate security findings from decompile result"""
        findings = []

        # Check for dangerous permissions
        dangerous_permissions = {
            "android.permission.READ_SMS": ("SMS Access", "high"),
            "android.permission.SEND_SMS": ("SMS Send", "high"),
            "android.permission.READ_CONTACTS": ("Contacts Access", "medium"),
            "android.permission.READ_CALL_LOG": ("Call Log Access", "high"),
            "android.permission.CAMERA": ("Camera Access", "medium"),
            "android.permission.RECORD_AUDIO": ("Audio Recording", "high"),
            "android.permission.ACCESS_FINE_LOCATION": ("Precise Location", "medium"),
            "android.permission.READ_EXTERNAL_STORAGE": ("Storage Read", "low"),
            "android.permission.WRITE_EXTERNAL_STORAGE": ("Storage Write", "medium"),
        }

        for perm in result.permissions:
            if perm in dangerous_permissions:
                name, severity = dangerous_permissions[perm]
                findings.append(
                    SecurityFinding(
                        title=f"Dangerous Permission: {name}",
                        description=f"App requests {perm}",
                        severity=severity,
                        location="AndroidManifest.xml",
                    )
                )

        # Check for exported components without permissions
        for activity in result.activities:
            if ".MainActivity" not in activity:
                findings.append(
                    SecurityFinding(
                        title=f"Exported Activity: {activity.split('.')[-1]}",
                        description="Activity may be exported and accessible by other apps",
                        severity="low",
                        location="AndroidManifest.xml",
                    )
                )

        # Check for sensitive strings
        sensitive_categories = ["api_key", "password", "private_key", "aws_key"]
        for string in result.strings:
            if string.category in sensitive_categories:
                findings.append(
                    SecurityFinding(
                        title=f"Sensitive String: {string.category}",
                        description=f"Found {string.category} in binary",
                        severity="high",
                        location=string.location,
                    )
                )

        # Check for missing protections
        expected_protections = [
            ProtectionType.ROOT_DETECTION,
            ProtectionType.CERTIFICATE_PINNING,
            ProtectionType.OBFUSCATION,
        ]

        for prot in expected_protections:
            if prot not in result.protections:
                findings.append(
                    SecurityFinding(
                        title=f"Missing Protection: {prot.value.replace('_', ' ').title()}",
                        description=f"{prot.value.replace('_', ' ').title()} not detected in binary",
                        severity="medium",
                        location="Binary analysis",
                    )
                )

        return findings

    def extract_strings(self, binary_path: Path, min_length: int = 8) -> List[StringFinding]:
        """
        Extract strings from binary.

        CLI-compatible method.
        """
        strings = []

        try:
            if binary_path.suffix.lower() == ".apk":
                with zipfile.ZipFile(binary_path, "r") as zf:
                    # Extract strings from DEX files
                    for name in zf.namelist():
                        if name.endswith(".dex"):
                            content = zf.read(name)
                            strings.extend(self._extract_strings_from_bytes(content, name, min_length))
            elif binary_path.suffix.lower() == ".ipa":
                with zipfile.ZipFile(binary_path, "r") as zf:
                    for name in zf.namelist():
                        if "/Payload/" in name and not name.endswith("/"):
                            try:
                                content = zf.read(name)
                                strings.extend(self._extract_strings_from_bytes(content, name, min_length))
                            except Exception:
                                pass
            else:
                content = binary_path.read_bytes()
                strings.extend(self._extract_strings_from_bytes(content, str(binary_path), min_length))

        except (zipfile.BadZipFile, OSError):
            pass

        return strings

    def _extract_strings_from_bytes(self, content: bytes, location: str, min_length: int) -> List[StringFinding]:
        """Extract strings from bytes"""
        strings = []

        # Patterns for categorization
        patterns = {
            "url": r'https?://[^\s"\'<>]+',
            "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            "api_key": r'(?:api[_-]?key|apikey)["\s:=]+["\']?([\w\-]{16,})["\']?',
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "password": r'(?:password|passwd|pwd)["\s:=]+["\']?([^\s"\']{4,})["\']?',
            "token": r'(?:token|secret)["\s:=]+["\']?([\w\-]{16,})["\']?',
        }

        # Extract ASCII strings
        ascii_pattern = rb"[\x20-\x7e]{" + str(min_length).encode() + rb",}"
        raw_strings = re.findall(ascii_pattern, content)

        for raw in raw_strings[:1000]:  # Limit to prevent excessive processing
            try:
                decoded = raw.decode("utf-8")

                # Categorize string
                category = "other"
                for cat, pattern in patterns.items():
                    if re.search(pattern, decoded, re.IGNORECASE):
                        category = cat
                        break

                if category != "other":  # Only include categorized strings
                    strings.append(
                        StringFinding(
                            value=decoded,
                            location=location,
                            category=category,
                            confidence=0.7,
                        )
                    )

            except UnicodeDecodeError:
                pass

        return strings

    def export_report(self, result: DecompileResult, output_path: Path) -> None:
        """Export analysis report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
