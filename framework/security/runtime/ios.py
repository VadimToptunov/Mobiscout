"""Analyzer extracted from runtime_protection (mechanical split; see runtime/base.py)."""

from pathlib import Path
from typing import ClassVar, List

from framework.security.runtime.base import (
    BaseProtectionAnalyzer,
    ProtectionCategory,
    ProtectionAnalysis,
)


class IOSProtectionAnalyzer(BaseProtectionAnalyzer):
    """
    iOS Runtime Protection Analyzer

    Analyzes iOS apps for runtime protection mechanisms.
    """

    EXTENSIONS: ClassVar[List[str]] = [".swift", ".m", ".h", ".plist"]

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
