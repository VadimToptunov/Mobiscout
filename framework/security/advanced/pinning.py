"""Analyzer extracted from advanced_security (mechanical split; see advanced/base.py)."""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Pattern, Set, Tuple, Union
from urllib.parse import parse_qs, urlparse

from framework.security.advanced.base import (
    OWASPMobileTop10,
    RiskLevel,
    SecurityVulnerability,
    SecretPattern,
)

logger = logging.getLogger(__name__)


class CertificatePinningAnalyzer:
    """
    Analyzes certificate pinning implementation

    Checks for proper SSL/TLS certificate pinning in mobile apps
    """

    def __init__(self):
        self.android_pinning_patterns = [
            # OkHttp CertificatePinner
            re.compile(r"CertificatePinner\.Builder\(\)", re.MULTILINE),
            re.compile(r'\.add\s*\(\s*["\'][^"\']+["\']\s*,\s*["\']sha256/', re.MULTILINE),
            # Network Security Config
            re.compile(r"<pin-set[^>]*>", re.MULTILINE),
            re.compile(r'<pin\s+digest=["\']SHA-256["\']>', re.MULTILINE),
            # TrustKit
            re.compile(r"TrustKit\.initWithConfiguration", re.MULTILINE),
        ]

        self.ios_pinning_patterns = [
            # TrustKit
            re.compile(r"TrustKit\.initSharedInstance", re.MULTILINE),
            # Alamofire
            re.compile(r"ServerTrustPolicy\.pinCertificates", re.MULTILINE),
            re.compile(r"ServerTrustPolicy\.pinPublicKeys", re.MULTILINE),
            # URLSession
            re.compile(r"URLAuthenticationChallenge", re.MULTILINE),
            re.compile(r"SecTrustEvaluate", re.MULTILINE),
        ]

        self.bypass_patterns = [
            # Common bypass indicators
            re.compile(r"trustAllCerts|trustAll|disableCertificateValidation", re.I),
            re.compile(r"ALLOW_ALL_HOSTNAME_VERIFIER", re.I),
            re.compile(r"setHostnameVerifier\s*\(\s*null", re.I),
            re.compile(r"X509TrustManager.*checkServerTrusted.*\{\s*\}", re.DOTALL),
            re.compile(r"NSAllowsArbitraryLoads.*true", re.I),
        ]

    def analyze_android(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Analyze Android app for certificate pinning"""
        vulnerabilities = []
        has_pinning = False
        has_bypass = False

        # Check for network security config
        network_config = source_dir / "res" / "xml" / "network_security_config.xml"
        if network_config.exists():
            content = network_config.read_text()
            if any(p.search(content) for p in self.android_pinning_patterns[2:4]):
                has_pinning = True

        # Scan Java/Kotlin files
        for ext in ["*.java", "*.kt"]:
            for file_path in source_dir.rglob(ext):
                content = file_path.read_text(errors="ignore")

                # Check for pinning implementation
                if any(p.search(content) for p in self.android_pinning_patterns):
                    has_pinning = True

                # Check for bypass patterns
                for pattern in self.bypass_patterns:
                    match = pattern.search(content)
                    if match:
                        has_bypass = True
                        line_num = content[: match.start()].count("\n") + 1
                        vulnerabilities.append(
                            SecurityVulnerability(
                                id=f"CERT-BYPASS-{hashlib.md5(str(file_path).encode()).hexdigest()[:8]}",
                                title="Certificate Validation Bypass Detected",
                                description="Code that bypasses SSL/TLS certificate validation was found. "
                                "This makes the app vulnerable to man-in-the-middle attacks.",
                                owasp_category=OWASPMobileTop10.M5_INSECURE_COMMUNICATION,
                                risk_level=RiskLevel.CRITICAL,
                                cvss_score=9.0,
                                cwe_ids=[295],  # CWE-295: Improper Certificate Validation
                                location=f"{file_path}:{line_num}",
                                evidence=f"Pattern: {pattern.pattern}",
                                remediation="Remove certificate validation bypass code. Implement proper "
                                "certificate pinning using OkHttp CertificatePinner or "
                                "Network Security Config.",
                                references=[
                                    "https://developer.android.com/training/articles/security-ssl",
                                    "https://owasp.org/www-community/controls/Certificate_and_Public_Key_Pinning",
                                ],
                            )
                        )

        # Check if pinning is missing entirely
        if not has_pinning and not has_bypass:
            vulnerabilities.append(
                SecurityVulnerability(
                    id="CERT-NO-PINNING",
                    title="No Certificate Pinning Implemented",
                    description="The app does not implement certificate pinning, making it vulnerable "
                    "to man-in-the-middle attacks using rogue certificates.",
                    owasp_category=OWASPMobileTop10.M5_INSECURE_COMMUNICATION,
                    risk_level=RiskLevel.HIGH,
                    cvss_score=7.5,
                    cwe_ids=[295],
                    location="Application-wide",
                    evidence="No certificate pinning patterns found in source code",
                    remediation="Implement certificate pinning:\n"
                    "1. Use Network Security Config (Android 7+)\n"
                    "2. Use OkHttp CertificatePinner\n"
                    "3. Use TrustKit library",
                    references=["https://developer.android.com/training/articles/security-config"],
                )
            )

        return vulnerabilities

    def analyze_ios(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Analyze iOS app for certificate pinning"""
        vulnerabilities = []
        has_pinning = False

        # Check Info.plist for ATS settings
        info_plist = source_dir / "Info.plist"
        if info_plist.exists():
            content = info_plist.read_text()
            if "NSAllowsArbitraryLoads" in content and "true" in content.lower():
                vulnerabilities.append(
                    SecurityVulnerability(
                        id="CERT-ATS-DISABLED",
                        title="App Transport Security Disabled",
                        description="NSAllowsArbitraryLoads is set to true, disabling App Transport Security. "
                        "This allows insecure HTTP connections.",
                        owasp_category=OWASPMobileTop10.M5_INSECURE_COMMUNICATION,
                        risk_level=RiskLevel.HIGH,
                        cvss_score=7.5,
                        cwe_ids=[319],  # CWE-319: Cleartext Transmission
                        location="Info.plist",
                        evidence="NSAllowsArbitraryLoads = true",
                        remediation="Remove NSAllowsArbitraryLoads or set it to false. "
                        "Configure specific exceptions if needed.",
                        references=[
                            "https://developer.apple.com/documentation/security/preventing_insecure_network_connections"
                        ],
                    )
                )

        # Scan Swift/Objective-C files
        for ext in ["*.swift", "*.m", "*.mm"]:
            for file_path in source_dir.rglob(ext):
                content = file_path.read_text(errors="ignore")

                if any(p.search(content) for p in self.ios_pinning_patterns):
                    has_pinning = True

        if not has_pinning:
            vulnerabilities.append(
                SecurityVulnerability(
                    id="CERT-NO-PINNING-IOS",
                    title="No Certificate Pinning Implemented",
                    description="The iOS app does not implement certificate pinning.",
                    owasp_category=OWASPMobileTop10.M5_INSECURE_COMMUNICATION,
                    risk_level=RiskLevel.HIGH,
                    cvss_score=7.5,
                    cwe_ids=[295],
                    location="Application-wide",
                    evidence="No certificate pinning patterns found",
                    remediation="Implement certificate pinning using TrustKit or URLSession delegate.",
                    references=[
                        "https://developer.apple.com/documentation/foundation/url_loading_system/handling_an_authentication_challenge"
                    ],
                )
            )

        return vulnerabilities


# ============================================================================
# Binary Security Analyzer
# ============================================================================
