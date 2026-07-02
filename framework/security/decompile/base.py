"""
Decompilation and Reverse Engineering Module

Binary analysis and decompilation for mobile applications.

Features:
- APK decompilation and analysis
- IPA analysis
- DEX file analysis
- Native library analysis
- String extraction
- Resource extraction
- Manifest analysis
- Smali code analysis
- Binary protection detection
"""

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


class ProtectionType(Enum):
    """Binary protection types"""

    OBFUSCATION = "obfuscation"
    ROOT_DETECTION = "root_detection"
    JAILBREAK_DETECTION = "jailbreak_detection"
    EMULATOR_DETECTION = "emulator_detection"
    DEBUG_DETECTION = "debug_detection"
    TAMPER_DETECTION = "tamper_detection"
    CERTIFICATE_PINNING = "certificate_pinning"
    CODE_SIGNING = "code_signing"
    ENCRYPTION = "encryption"
    PACKING = "packing"


class BinaryType(Enum):
    """Binary types"""

    APK = "apk"
    AAB = "aab"
    IPA = "ipa"
    DEX = "dex"
    SO = "so"
    DYLIB = "dylib"


@dataclass
class StringFinding:
    """Extracted string finding"""

    value: str
    location: str
    category: str  # url, api_key, password, etc.
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "location": self.location,
            "category": self.category,
            "confidence": self.confidence,
        }


@dataclass
class ProtectionInfo:
    """Protection mechanism info - for CLI compatibility"""

    name: str
    detected: bool
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "detected": self.detected,
            "details": self.details,
        }


@dataclass
class NativeLibInfo:
    """Native library info - for CLI compatibility"""

    name: str
    path: str
    architectures: List[str] = field(default_factory=list)
    size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "architectures": self.architectures,
            "size": self.size,
        }


@dataclass
class SecurityFinding:
    """Security finding from decompilation - for CLI compatibility"""

    title: str
    description: str
    severity: str  # critical, high, medium, low
    location: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "location": self.location,
        }


@dataclass
class DecompileResult:
    """Decompilation result"""

    binary_type: BinaryType
    binary_path: str
    output_dir: str
    package_name: Optional[str]
    version_name: Optional[str]
    version_code: Optional[int]
    min_sdk: Optional[int]
    target_sdk: Optional[int]
    permissions: List[str]
    activities: List[str]
    services: List[str]
    receivers: List[str]
    providers: List[str]
    native_libs: List[str]
    strings: List[StringFinding]
    protections: List[ProtectionType]
    hashes: Dict[str, str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    # CLI compatibility fields
    security_findings: List[SecurityFinding] = field(default_factory=list)
    _protection_infos: List[ProtectionInfo] = field(default_factory=list)
    _native_lib_infos: List[NativeLibInfo] = field(default_factory=list)

    # CLI-compatible property aliases
    @property
    def version(self) -> str:
        """Alias for version_name for CLI compatibility"""
        return self.version_name or "unknown"

    @property
    def sha256(self) -> str:
        """Direct SHA256 access for CLI compatibility"""
        return self.hashes.get("sha256", "")

    @property
    def size_bytes(self) -> int:
        """File size for CLI compatibility"""
        return self.metadata.get("file_size", 0)

    @property
    def interesting_strings(self) -> List[StringFinding]:
        """Alias for strings for CLI compatibility"""
        return self.strings

    @property
    def protection_infos(self) -> List[ProtectionInfo]:
        """Protection info objects for CLI compatibility"""
        if self._protection_infos:
            return self._protection_infos

        # Convert ProtectionType list to ProtectionInfo list
        infos = []
        all_types = list(ProtectionType)

        for ptype in all_types:
            detected = ptype in self.protections
            infos.append(
                ProtectionInfo(
                    name=ptype.value.replace("_", " ").title(),
                    detected=detected,
                    details=f"{'Detected' if detected else 'Not found'} in binary analysis",
                )
            )

        return infos

    @property
    def native_lib_infos(self) -> List[NativeLibInfo]:
        """Native library info objects for CLI compatibility"""
        if self._native_lib_infos:
            return self._native_lib_infos

        # Convert native_libs strings to NativeLibInfo objects
        infos = []
        for lib_path in self.native_libs:
            path = Path(lib_path)
            # Extract architecture from path (e.g., /lib/arm64-v8a/libname.so)
            parts = path.parts
            arch = []
            for part in parts:
                if part in ["arm64-v8a", "armeabi-v7a", "x86", "x86_64", "armeabi"]:
                    arch.append(part)

            infos.append(
                NativeLibInfo(
                    name=path.name,
                    path=lib_path,
                    architectures=arch if arch else ["unknown"],
                )
            )

        return infos

    def to_dict(self) -> Dict[str, Any]:
        return {
            "binary_type": self.binary_type.value,
            "binary_path": self.binary_path,
            "output_dir": self.output_dir,
            "package_name": self.package_name,
            "version": self.version,
            "version_name": self.version_name,
            "version_code": self.version_code,
            "min_sdk": self.min_sdk,
            "target_sdk": self.target_sdk,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "permissions": self.permissions,
            "activities": self.activities,
            "services": self.services,
            "receivers": self.receivers,
            "providers": self.providers,
            "native_libs": [lib.to_dict() for lib in self.native_lib_infos],
            "interesting_strings": [
                {"value": s.value[:100], "category": s.category, "confidence": s.confidence} for s in self.strings[:50]
            ],
            "protections": [p.to_dict() for p in self.protection_infos],
            "security_findings": [f.to_dict() for f in self.security_findings],
            "hashes": self.hashes,
            "metadata": self.metadata,
        }
