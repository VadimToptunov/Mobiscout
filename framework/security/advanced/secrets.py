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


class HardcodedSecretsScanner:
    """
    Advanced hardcoded secrets detection

    Detects API keys, tokens, passwords, private keys with high accuracy
    using pattern matching, entropy analysis, and context validation.
    """

    def __init__(self):
        self.patterns = self._initialize_patterns()
        self._false_positive_patterns = [
            re.compile(r"example|test|sample|placeholder|xxx|your[_-]?", re.I),
            re.compile(r"<[^>]+>"),  # XML/HTML placeholders
            re.compile(r"\$\{[^}]+\}"),  # Variable substitution
            re.compile(r"%[sd]"),  # Format strings
        ]

    def _initialize_patterns(self) -> List[SecretPattern]:
        """Initialize comprehensive secret detection patterns"""
        return [
            # AWS
            SecretPattern(
                "AWS Access Key ID",
                r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
                RiskLevel.CRITICAL,
                4.0,
            ),
            SecretPattern(
                "AWS Secret Access Key",
                r'(?:aws)?[_\-]?secret[_\-]?(?:access)?[_\-]?key["\'\s:=]+[A-Za-z0-9/+=]{40}',
                RiskLevel.CRITICAL,
                4.5,
            ),
            # Google
            SecretPattern("Google API Key", r"AIza[0-9A-Za-z\-_]{35}", RiskLevel.HIGH, 4.0),
            SecretPattern(
                "Google OAuth Client ID", r"[0-9]+-[a-z0-9_]{32}\.apps\.googleusercontent\.com", RiskLevel.MEDIUM, 3.5
            ),
            SecretPattern(
                "Firebase API Key",
                r'(?:firebase|FIREBASE)[_\-]?(?:API)?[_\-]?KEY["\'\s:=]+[A-Za-z0-9\-_]{39}',
                RiskLevel.HIGH,
                4.0,
            ),
            # GitHub
            SecretPattern("GitHub Token", r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}", RiskLevel.CRITICAL, 4.5),
            SecretPattern(
                "GitHub OAuth",
                r'github[_\-]?(?:oauth)?[_\-]?(?:token|secret)["\'\s:=]+[A-Za-z0-9_]{40}',
                RiskLevel.CRITICAL,
                4.0,
            ),
            # Stripe
            SecretPattern("Stripe API Key", r"(?:sk|pk)_(?:test|live)_[A-Za-z0-9]{24,}", RiskLevel.CRITICAL, 4.5),
            # Twilio
            SecretPattern("Twilio API Key", r"SK[a-f0-9]{32}", RiskLevel.HIGH, 4.0),
            SecretPattern(
                "Twilio Auth Token", r'twilio[_\-]?auth[_\-]?token["\'\s:=]+[a-f0-9]{32}', RiskLevel.HIGH, 4.0
            ),
            # Slack
            SecretPattern("Slack Token", r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*", RiskLevel.HIGH, 4.0),
            SecretPattern(
                "Slack Webhook",
                r"https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[A-Za-z0-9]{24}",
                RiskLevel.MEDIUM,
                3.5,
            ),
            # Generic tokens and keys
            SecretPattern(
                "Generic API Key", r'(?:api[_\-]?key|apikey)["\'\s:=]+[A-Za-z0-9\-_]{20,}', RiskLevel.HIGH, 3.5
            ),
            SecretPattern(
                "Generic Secret",
                r'(?:secret|SECRET)[_\-]?(?:KEY|key)?["\'\s:=]+[A-Za-z0-9\-_/+=]{16,}',
                RiskLevel.HIGH,
                4.0,
            ),
            SecretPattern(
                "Bearer Token", r"[Bb]earer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+", RiskLevel.HIGH, 4.0
            ),
            # Private Keys
            SecretPattern(
                "RSA Private Key",
                r"-----BEGIN (?:RSA )?PRIVATE KEY-----",
                RiskLevel.CRITICAL,
                0.0,  # No entropy check needed
            ),
            SecretPattern("EC Private Key", r"-----BEGIN EC PRIVATE KEY-----", RiskLevel.CRITICAL, 0.0),
            SecretPattern("PGP Private Key", r"-----BEGIN PGP PRIVATE KEY BLOCK-----", RiskLevel.CRITICAL, 0.0),
            # Database
            SecretPattern(
                "Database Connection String",
                r'(?:mongodb|mysql|postgres|redis)://[^"\'\s]+:[^"\'\s]+@[^"\'\s]+',
                RiskLevel.CRITICAL,
                3.0,
            ),
            # Passwords
            SecretPattern(
                "Password in Code", r'(?:password|passwd|pwd)["\'\s:=]+["\'][^"\']{8,}["\']', RiskLevel.HIGH, 3.0
            ),
            # JWT
            SecretPattern("JWT Token", r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+", RiskLevel.MEDIUM, 4.0),
            # Mobile-specific
            SecretPattern("Google Maps API Key", r"AIza[0-9A-Za-z\\-_]{35}", RiskLevel.MEDIUM, 4.0),
            SecretPattern(
                "Facebook App Secret",
                r'(?:facebook|fb)[_\-]?(?:app)?[_\-]?secret["\'\s:=]+[a-f0-9]{32}',
                RiskLevel.HIGH,
                4.0,
            ),
        ]

    def calculate_shannon_entropy(self, data: str) -> float:
        """Calculate Shannon entropy of a string"""
        if not data:
            return 0.0

        entropy = 0.0
        for char_count in [data.count(c) for c in set(data)]:
            if char_count > 0:
                freq = char_count / len(data)
                entropy -= freq * (freq and __import__("math").log2(freq))

        return entropy

    def is_false_positive(self, match: str, context: str) -> bool:
        """Check if match is likely a false positive"""
        # Check against false positive patterns
        for fp_pattern in self._false_positive_patterns:
            if fp_pattern.search(match) or fp_pattern.search(context):
                return True

        # Check for common test values
        test_indicators = ["test", "example", "sample", "demo", "fake", "mock"]
        context_lower = context.lower()
        if any(indicator in context_lower for indicator in test_indicators):
            return True

        return False

    def scan_content(self, content: str, filename: str = "unknown") -> List[SecurityVulnerability]:
        """Scan content for hardcoded secrets"""
        vulnerabilities = []

        for pattern in self.patterns:
            for match in pattern.pattern.finditer(content):
                matched_text = match.group(0)

                # Get surrounding context (100 chars before and after)
                start = max(0, match.start() - 100)
                end = min(len(content), match.end() + 100)
                context = content[start:end]

                # Check for false positives
                if self.is_false_positive(matched_text, context):
                    continue

                # Entropy check (if threshold > 0)
                if pattern.entropy_threshold > 0:
                    # Extract the actual secret value from the match
                    secret_value = re.sub(r'^[^:=]+[:=\s"\']+', "", matched_text)
                    secret_value = secret_value.strip("\"'")

                    entropy = self.calculate_shannon_entropy(secret_value)
                    if entropy < pattern.entropy_threshold:
                        continue

                # Calculate line number
                line_num = content[: match.start()].count("\n") + 1

                vuln_id = hashlib.sha256(f"{filename}:{line_num}:{pattern.name}".encode()).hexdigest()[:12]

                vulnerabilities.append(
                    SecurityVulnerability(
                        id=f"SECRET-{vuln_id}",
                        title=f"Hardcoded {pattern.name} Detected",
                        description=f"A hardcoded {pattern.name} was found in the source code. "
                        f"This could lead to unauthorized access if the code is exposed.",
                        owasp_category=OWASPMobileTop10.M1_IMPROPER_CREDENTIAL_USAGE,
                        risk_level=pattern.severity,
                        cvss_score=8.5 if pattern.severity == RiskLevel.CRITICAL else 7.0,
                        cwe_ids=[798, 259],  # CWE-798: Hardcoded Credentials
                        location=f"{filename}:{line_num}",
                        evidence=f"Pattern: {pattern.name}\nMatch: {matched_text[:50]}...",
                        remediation="Remove hardcoded secrets and use secure secret management:\n"
                        "1. Use environment variables\n"
                        "2. Use secure vaults (AWS Secrets Manager, HashiCorp Vault)\n"
                        "3. Use Android Keystore / iOS Keychain for mobile apps\n"
                        "4. Rotate the compromised credentials immediately",
                        references=[
                            "https://owasp.org/www-community/vulnerabilities/Use_of_hard-coded_password",
                            "https://cwe.mitre.org/data/definitions/798.html",
                        ],
                    )
                )

        return vulnerabilities

    def scan_file(self, file_path: Path) -> List[SecurityVulnerability]:
        """Scan a file for hardcoded secrets"""
        try:
            content = file_path.read_text(errors="ignore")
            return self.scan_content(content, str(file_path))
        except Exception as e:
            logger.warning(f"Could not scan {file_path}: {e}")
            return []

    def scan_directory(self, directory: Path, extensions: Optional[List[str]] = None) -> List[SecurityVulnerability]:
        """Scan directory recursively for hardcoded secrets"""
        if extensions is None:
            extensions = [
                ".py",
                ".java",
                ".kt",
                ".swift",
                ".m",
                ".h",
                ".js",
                ".ts",
                ".jsx",
                ".tsx",
                ".json",
                ".xml",
                ".yml",
                ".yaml",
                ".properties",
                ".gradle",
                ".plist",
                ".env",
                ".config",
                ".cfg",
                ".ini",
            ]

        vulnerabilities = []
        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix in extensions:
                vulnerabilities.extend(self.scan_file(file_path))

        return vulnerabilities


# ============================================================================
# Certificate Pinning Analyzer
# ============================================================================
