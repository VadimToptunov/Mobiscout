"""Analyzer extracted from runtime_protection (mechanical split; see runtime/base.py)."""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from framework.security.runtime.base import (
    ProtectionCategory,
    ImplementationQuality,
    ProtectionIndicator,
    ProtectionAnalysis,
    ProtectionStatus,
    BypassMethod,
    RuntimeProtectionResult,
    QuickCheckResult,
)


class AndroidProtectionAnalyzer:
    """
    Android Runtime Protection Analyzer

    Analyzes Android apps for runtime protection mechanisms.
    """

    # Root detection patterns
    ROOT_DETECTION_PATTERNS = {
        # Binary checks
        r"/system/bin/su": ("su binary check", "easy"),
        r"/system/xbin/su": ("su binary check", "easy"),
        r"/sbin/su": ("su binary check", "easy"),
        r"which su": ("su path check", "easy"),
        # Package checks
        r"com\.noshufou\.android\.su": ("SuperSU package", "moderate"),
        r"com\.thirdparty\.superuser": ("Superuser package", "moderate"),
        r"eu\.chainfire\.supersu": ("SuperSU package", "moderate"),
        r"com\.koushikdutta\.superuser": ("Superuser package", "moderate"),
        r"com\.topjohnwu\.magisk": ("Magisk package", "moderate"),
        # Method patterns
        r"isRooted|checkRoot|detectRoot": ("Root detection method", "moderate"),
        r"RootBeer|RootChecker": ("Root detection library", "hard"),
        r"SafetyNet": ("SafetyNet attestation", "hard"),
        # File checks
        r"/system/app/Superuser": ("Superuser app check", "easy"),
        r"/data/local/bin/su": ("Local su check", "easy"),
    }

    # Emulator detection patterns
    EMULATOR_DETECTION_PATTERNS = {
        r"generic": ("Generic device check", "easy"),
        r"goldfish": ("Goldfish check", "easy"),
        r"vbox86": ("VirtualBox check", "moderate"),
        r"genymotion": ("Genymotion check", "moderate"),
        r"sdk_google": ("SDK image check", "easy"),
        r"Andy|BlueStacks|Nox": ("Known emulator check", "moderate"),
        r"isEmulator|detectEmulator": ("Emulator detection method", "moderate"),
        r"Build\.FINGERPRINT": ("Fingerprint analysis", "moderate"),
        r"Build\.HARDWARE": ("Hardware analysis", "moderate"),
        r"/dev/qemu_pipe": ("QEMU pipe check", "hard"),
        r"/dev/socket/qemud": ("QEMU socket check", "hard"),
    }

    # Debug detection patterns
    DEBUG_DETECTION_PATTERNS = {
        r"Debug\.isDebuggerConnected": ("Debugger check", "easy"),
        r"isDebuggerConnected": ("Debugger check", "easy"),
        r"waitForDebugger": ("Debugger wait", "easy"),
        r"android:debuggable": ("Debuggable flag", "easy"),
        r"JDWP": ("JDWP detection", "moderate"),
        r"/proc/self/status.*TracerPid": ("TracerPid check", "hard"),
        r"ptrace": ("Ptrace detection", "hard"),
    }

    # Frida/Hook detection patterns
    FRIDA_DETECTION_PATTERNS = {
        r"frida": ("Frida string", "easy"),
        r"libfrida": ("Frida library", "moderate"),
        r"27042": ("Frida default port", "moderate"),
        r"/data/local/tmp": ("Frida injection path", "moderate"),
        r"xposed": ("Xposed detection", "moderate"),
        r"de\.robv\.android\.xposed": ("Xposed package", "moderate"),
        r"substrate": ("Substrate detection", "moderate"),
        r"cydia\.substrate": ("Substrate package", "moderate"),
    }

    # Tamper detection patterns
    TAMPER_DETECTION_PATTERNS = {
        r"PackageManager\.GET_SIGNATURES": ("Signature check", "moderate"),
        r"getSigningInfo": ("Signing info check", "moderate"),
        r"checkSignature": ("Signature verification", "moderate"),
        r"CRC32|checksum": ("Checksum verification", "hard"),
        r"dexFile\.loadDex": ("DEX loading check", "hard"),
        r"classes\.dex": ("DEX file check", "moderate"),
    }

    # SSL Pinning patterns
    SSL_PINNING_PATTERNS = {
        r"CertificatePinner": ("OkHttp pinning", "hard"),
        r"TrustManagerFactory": ("Custom TrustManager", "moderate"),
        r"X509TrustManager": ("Custom X509TrustManager", "moderate"),
        r"checkServerTrusted": ("Server cert check", "moderate"),
        r"network_security_config": ("Network security config", "hard"),
        r"<pin-set": ("Pin set configuration", "hard"),
    }

    def analyze_source(self, source_dir: Path) -> List[ProtectionAnalysis]:
        """Analyze Android source code for protection mechanisms"""
        analyses = []

        # Collect all indicators
        root_indicators = self._find_patterns(
            source_dir, self.ROOT_DETECTION_PATTERNS, ProtectionCategory.ROOT_DETECTION
        )
        emulator_indicators = self._find_patterns(
            source_dir, self.EMULATOR_DETECTION_PATTERNS, ProtectionCategory.EMULATOR_DETECTION
        )
        debug_indicators = self._find_patterns(
            source_dir, self.DEBUG_DETECTION_PATTERNS, ProtectionCategory.DEBUG_DETECTION
        )
        frida_indicators = self._find_patterns(
            source_dir, self.FRIDA_DETECTION_PATTERNS, ProtectionCategory.FRIDA_DETECTION
        )
        tamper_indicators = self._find_patterns(
            source_dir, self.TAMPER_DETECTION_PATTERNS, ProtectionCategory.TAMPER_DETECTION
        )
        ssl_indicators = self._find_patterns(source_dir, self.SSL_PINNING_PATTERNS, ProtectionCategory.SSL_PINNING)

        # Analyze each category
        analyses.append(
            self._analyze_category(
                ProtectionCategory.ROOT_DETECTION,
                root_indicators,
                [
                    "Implement multiple root detection methods",
                    "Use SafetyNet attestation for strong verification",
                    "Combine binary, package, and property checks",
                    "Check for Magisk hide and similar bypass tools",
                ],
            )
        )

        analyses.append(
            self._analyze_category(
                ProtectionCategory.EMULATOR_DETECTION,
                emulator_indicators,
                [
                    "Check multiple device properties",
                    "Analyze build fingerprint and hardware",
                    "Check for emulator-specific files",
                    "Monitor performance characteristics",
                ],
            )
        )

        analyses.append(
            self._analyze_category(
                ProtectionCategory.DEBUG_DETECTION,
                debug_indicators,
                [
                    "Check debugger connection status",
                    "Monitor TracerPid in /proc/self/status",
                    "Use timing-based anti-debug",
                    "Implement multi-threaded debug detection",
                ],
            )
        )

        analyses.append(
            self._analyze_category(
                ProtectionCategory.FRIDA_DETECTION,
                frida_indicators,
                [
                    "Scan for Frida artifacts and libraries",
                    "Monitor for Frida's default port (27042)",
                    "Check for Xposed framework",
                    "Implement memory scanning for hooks",
                ],
            )
        )

        analyses.append(
            self._analyze_category(
                ProtectionCategory.TAMPER_DETECTION,
                tamper_indicators,
                [
                    "Verify APK signature at runtime",
                    "Check DEX file integrity",
                    "Implement checksum verification",
                    "Use code obfuscation to hinder analysis",
                ],
            )
        )

        analyses.append(
            self._analyze_category(
                ProtectionCategory.SSL_PINNING,
                ssl_indicators,
                [
                    "Implement certificate pinning with OkHttp",
                    "Use network_security_config.xml",
                    "Pin multiple certificates for redundancy",
                    "Implement backup pins for certificate rotation",
                ],
            )
        )

        return analyses

    def _find_patterns(
        self, source_dir: Path, patterns: Dict[str, tuple], category: ProtectionCategory
    ) -> List[ProtectionIndicator]:
        """Find protection patterns in source code"""
        indicators = []

        extensions = [".java", ".kt", ".xml", ".smali"]

        for ext in extensions:
            for file_path in source_dir.rglob(f"*{ext}"):
                try:
                    content = file_path.read_text(errors="ignore")
                    lines = content.splitlines()

                    for pattern, (desc, difficulty) in patterns.items():
                        for i, line in enumerate(lines, 1):
                            if re.search(pattern, line, re.IGNORECASE):
                                indicators.append(
                                    ProtectionIndicator(
                                        category=category,
                                        indicator=pattern,
                                        location=str(file_path),
                                        line_number=i,
                                        description=desc,
                                        bypass_difficulty=difficulty,
                                    )
                                )
                except (OSError, UnicodeDecodeError):
                    pass

        return indicators

    def _analyze_category(
        self, category: ProtectionCategory, indicators: List[ProtectionIndicator], recommendations: List[str]
    ) -> ProtectionAnalysis:
        """Analyze a protection category"""
        if not indicators:
            return ProtectionAnalysis(
                category=category,
                implemented=False,
                quality=ImplementationQuality.NONE,
                indicators=[],
                recommendations=recommendations,
                score=0.0,
            )

        # Calculate quality based on bypass difficulty
        hard_count = len([i for i in indicators if i.bypass_difficulty == "hard"])
        moderate_count = len([i for i in indicators if i.bypass_difficulty == "moderate"])
        easy_count = len([i for i in indicators if i.bypass_difficulty == "easy"])

        total = len(indicators)
        weighted_score = (hard_count * 3 + moderate_count * 2 + easy_count) / (total * 3) * 100

        if weighted_score >= 70:
            quality = ImplementationQuality.STRONG
        elif weighted_score >= 40:
            quality = ImplementationQuality.MODERATE
        else:
            quality = ImplementationQuality.WEAK

        # Filter recommendations to what's not implemented
        remaining_recommendations = recommendations[:3] if quality == ImplementationQuality.WEAK else []

        return ProtectionAnalysis(
            category=category,
            implemented=True,
            quality=quality,
            indicators=indicators,
            recommendations=remaining_recommendations,
            score=weighted_score,
        )
