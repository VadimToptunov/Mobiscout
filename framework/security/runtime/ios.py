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


class IOSProtectionAnalyzer:
    """
    iOS Runtime Protection Analyzer

    Analyzes iOS apps for runtime protection mechanisms.
    """

    # Jailbreak detection patterns
    JAILBREAK_DETECTION_PATTERNS = {
        r"/Applications/Cydia\.app": ("Cydia app check", "easy"),
        r"/Library/MobileSubstrate": ("Substrate check", "easy"),
        r"/bin/bash": ("Bash shell check", "easy"),
        r"/usr/sbin/sshd": ("SSH daemon check", "easy"),
        r"/etc/apt": ("APT check", "easy"),
        r"/private/var/lib/apt": ("APT lib check", "easy"),
        r"cydia://": ("Cydia URL scheme", "moderate"),
        r"isJailbroken": ("Jailbreak method", "moderate"),
        r"canOpenURL.*cydia": ("Cydia URL check", "moderate"),
        r"fileExistsAtPath.*cydia": ("Cydia file check", "moderate"),
        r"fork\(\)": ("Fork check", "hard"),
        r"sysctl.*P_TRACED": ("Sysctl trace check", "hard"),
    }

    # Debug detection patterns
    IOS_DEBUG_DETECTION_PATTERNS = {
        r"sysctl.*P_TRACED": ("Sysctl trace check", "hard"),
        r"ptrace": ("Ptrace detection", "hard"),
        r"getppid": ("Parent PID check", "moderate"),
        r"isBeingDebugged": ("Debug check method", "moderate"),
        r"SIGSTOP": ("Signal handling", "hard"),
    }

    # Frida detection patterns
    IOS_FRIDA_DETECTION_PATTERNS = {
        r"frida": ("Frida string", "easy"),
        r"27042": ("Frida default port", "moderate"),
        r"_frida": ("Frida symbol", "moderate"),
        r"gum-js-loop": ("Frida gadget", "hard"),
        r"/usr/lib/frida": ("Frida library", "moderate"),
    }

    # SSL Pinning patterns
    IOS_SSL_PINNING_PATTERNS = {
        r"TrustKit": ("TrustKit library", "hard"),
        r"Alamofire.*ServerTrustManager": ("Alamofire pinning", "hard"),
        r"SecTrustEvaluate": ("SecTrust evaluation", "moderate"),
        r"URLSession.*delegate": ("URLSession delegate", "moderate"),
        r"NSAppTransportSecurity": ("ATS configuration", "moderate"),
    }

    def analyze_source(self, source_dir: Path) -> List[ProtectionAnalysis]:
        """Analyze iOS source code for protection mechanisms"""
        analyses = []

        # Collect indicators
        jb_indicators = self._find_patterns(
            source_dir, self.JAILBREAK_DETECTION_PATTERNS, ProtectionCategory.JAILBREAK_DETECTION
        )
        debug_indicators = self._find_patterns(
            source_dir, self.IOS_DEBUG_DETECTION_PATTERNS, ProtectionCategory.DEBUG_DETECTION
        )
        frida_indicators = self._find_patterns(
            source_dir, self.IOS_FRIDA_DETECTION_PATTERNS, ProtectionCategory.FRIDA_DETECTION
        )
        ssl_indicators = self._find_patterns(source_dir, self.IOS_SSL_PINNING_PATTERNS, ProtectionCategory.SSL_PINNING)

        # Analyze each category
        analyses.append(
            self._analyze_category(
                ProtectionCategory.JAILBREAK_DETECTION,
                jb_indicators,
                [
                    "Check for jailbreak-related files and directories",
                    "Verify URL scheme availability (cydia://)",
                    "Use fork() to detect jailbreak bypass",
                    "Implement sysctl checks",
                ],
            )
        )

        analyses.append(
            self._analyze_category(
                ProtectionCategory.DEBUG_DETECTION,
                debug_indicators,
                [
                    "Use sysctl to check P_TRACED flag",
                    "Implement ptrace(PT_DENY_ATTACH)",
                    "Monitor for debug exceptions",
                    "Check parent process ID",
                ],
            )
        )

        analyses.append(
            self._analyze_category(
                ProtectionCategory.FRIDA_DETECTION,
                frida_indicators,
                [
                    "Scan for Frida artifacts",
                    "Monitor network connections for Frida ports",
                    "Check for Frida libraries in memory",
                    "Implement anti-instrumentation checks",
                ],
            )
        )

        analyses.append(
            self._analyze_category(
                ProtectionCategory.SSL_PINNING,
                ssl_indicators,
                [
                    "Use TrustKit for certificate pinning",
                    "Implement custom URLSession delegate",
                    "Configure ATS properly in Info.plist",
                    "Pin both leaf and intermediate certificates",
                ],
            )
        )

        return analyses

    def _find_patterns(
        self, source_dir: Path, patterns: Dict[str, tuple], category: ProtectionCategory
    ) -> List[ProtectionIndicator]:
        """Find protection patterns in iOS source"""
        indicators = []

        extensions = [".swift", ".m", ".h", ".plist"]

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

        remaining_recommendations = recommendations[:3] if quality == ImplementationQuality.WEAK else []

        return ProtectionAnalysis(
            category=category,
            implemented=True,
            quality=quality,
            indicators=indicators,
            recommendations=remaining_recommendations,
            score=weighted_score,
        )
