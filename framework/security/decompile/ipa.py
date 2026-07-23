"""Analyzer extracted from decompiler (mechanical split; see decompile/base.py)."""

import hashlib
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from framework.security.decompile.base import (
    ProtectionType,
    BinaryType,
    StringFinding,
    DecompileResult,
)


class IPAAnalyzer:
    """
    IPA Analysis

    Analyzes iOS IPA files for security information.
    """

    # Sensitive string patterns (iOS specific)
    SENSITIVE_PATTERNS = {
        "url": r'https?://[^\s"\'<>]+',
        "api_key": r'(?:api[_-]?key|apikey|api_secret)["\s:=]+["\']?([\w\-]{20,})["\']?',
        "bundle_id": r"[a-zA-Z0-9\-\.]+\.[a-zA-Z0-9\-\.]+",
        "entitlement": r"<key>([^<]+)</key>",
    }

    # Jailbreak detection indicators
    JAILBREAK_INDICATORS = [
        "cydia",
        "substrate",
        "jailbreak",
        "JailBroken",
        "/Applications/Cydia.app",
        "/Library/MobileSubstrate",
        "/bin/bash",
        "/usr/sbin/sshd",
        "/etc/apt",
        "isJailbroken",
        "detectJailbreak",
    ]

    def analyze(self, ipa_path: Path, output_dir: Optional[Path] = None) -> DecompileResult:
        """Analyze IPA file"""
        if not ipa_path.exists():
            raise FileNotFoundError(f"IPA not found: {ipa_path}")

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="ipa_analyze_"))
        else:
            output_dir.mkdir(parents=True, exist_ok=True)

        # Calculate hashes
        hashes = self._calculate_hashes(ipa_path)

        # Extract IPA
        extract_dir = output_dir / "extracted"
        with zipfile.ZipFile(ipa_path, "r") as zf:
            zf.extractall(extract_dir)

        # Find the .app bundle
        payload_dir = extract_dir / "Payload"
        app_bundle = None
        if payload_dir.exists():
            for item in payload_dir.iterdir():
                if item.suffix == ".app":
                    app_bundle = item
                    break

        # Parse Info.plist
        info_plist = {}
        if app_bundle:
            plist_path = app_bundle / "Info.plist"
            if plist_path.exists():
                info_plist = self._parse_plist(plist_path)

        # Extract strings from binary
        strings = []
        if app_bundle:
            # Find main binary
            binary_name = info_plist.get("CFBundleExecutable", app_bundle.stem)
            binary_path = app_bundle / binary_name
            if binary_path.exists():
                strings = self._extract_binary_strings(binary_path)

        # Detect protections
        protections = self._detect_protections(strings)

        # Find frameworks
        frameworks = []
        if app_bundle:
            frameworks_dir = app_bundle / "Frameworks"
            if frameworks_dir.exists():
                for fw in frameworks_dir.iterdir():
                    if fw.suffix == ".framework":
                        frameworks.append(fw.name)

        return DecompileResult(
            binary_type=BinaryType.IPA,
            binary_path=str(ipa_path),
            output_dir=str(output_dir),
            package_name=info_plist.get("CFBundleIdentifier"),
            version_name=info_plist.get("CFBundleShortVersionString"),
            version_code=None,
            min_sdk=None,
            target_sdk=None,
            permissions=[],  # iOS uses entitlements
            activities=[],  # Not applicable to iOS
            services=[],
            receivers=[],
            providers=[],
            native_libs=frameworks,
            strings=strings,
            protections=protections,
            hashes=hashes,
            metadata={
                "bundle_name": info_plist.get("CFBundleName"),
                "minimum_os": info_plist.get("MinimumOSVersion"),
                "device_family": info_plist.get("UIDeviceFamily"),
                "ats_settings": info_plist.get("NSAppTransportSecurity", {}),
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

    def _parse_plist(self, plist_path: Path) -> Dict[str, Any]:
        """Parse Info.plist"""
        try:
            import plistlib

            with open(plist_path, "rb") as f:
                plist: Dict[str, Any] = plistlib.load(f)
                return plist
        except (OSError, Exception):
            return {}

    def _extract_binary_strings(self, binary_path: Path) -> List[StringFinding]:
        """Extract strings from Mach-O binary"""
        strings = []

        try:
            content = binary_path.read_bytes()

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
                                    location=str(binary_path),
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

    def _detect_protections(self, strings: List[StringFinding]) -> List[ProtectionType]:
        """Detect binary protections"""
        protections = []

        all_strings = {s.value.lower() for s in strings}

        # Check jailbreak detection
        if any(indicator.lower() in s for s in all_strings for indicator in self.JAILBREAK_INDICATORS):
            protections.append(ProtectionType.JAILBREAK_DETECTION)

        # Check for certificate pinning
        pinning_indicators = ["trustkit", "alamofire", "urlsessiondelegate"]
        if any(indicator in s for s in all_strings for indicator in pinning_indicators):
            protections.append(ProtectionType.CERTIFICATE_PINNING)

        return protections
