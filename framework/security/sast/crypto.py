"""Analyzer extracted from sast_analyzer (mechanical split; see sast/base.py)."""

import ast
import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET

from framework.security.sast.base import (
    VulnerabilityType,
    Severity,
    TaintSource,
    TaintSink,
    TaintFlow,
    SASTFinding,
    SASTResult,
)

logger = logging.getLogger(__name__)


class CryptoAnalyzer:
    """
    Cryptographic Weakness Analyzer

    Detects insecure cryptographic implementations.
    """

    # Weak algorithms
    WEAK_ALGORITHMS = {
        "MD5": ("CWE-327", "MD5 is cryptographically broken"),
        "SHA1": ("CWE-327", "SHA1 is considered weak for security purposes"),
        "DES": ("CWE-327", "DES has insufficient key length"),
        "3DES": ("CWE-327", "Triple DES is deprecated"),
        "RC4": ("CWE-327", "RC4 has multiple vulnerabilities"),
        "RC2": ("CWE-327", "RC2 is considered weak"),
        "Blowfish": ("CWE-327", "Blowfish with small key sizes is weak"),
        "ECB": ("CWE-327", "ECB mode doesn't provide semantic security"),
    }

    # Insecure random
    INSECURE_RANDOM = [
        "random.random",
        "random.randint",
        "random.choice",
        "Math.random",
        "java.util.Random",
        "arc4random",  # iOS - not for crypto
    ]

    # Hardcoded key patterns
    KEY_PATTERNS = [
        r'["\']?(?:aes|des|rsa|hmac)?[_-]?(?:key|secret|password)["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
        r'(?:private|secret|encryption)[_-]?key\s*=\s*["\'][^"\']+["\']',
        r'iv\s*=\s*["\'][0-9a-fA-F]{16,}["\']',
        r'nonce\s*=\s*["\'][0-9a-fA-F]+["\']',
    ]

    def analyze(self, file_path: Path) -> List[SASTFinding]:
        """Analyze file for cryptographic weaknesses"""
        findings = []

        try:
            content = file_path.read_text()
            lines = content.splitlines()

            for i, line in enumerate(lines, 1):
                lower_line = line.lower()

                # Check weak algorithms. Match on word boundaries, not as a
                # substring: "DES" must not fire on "describe"/"nodes"/"used",
                # nor "ECB"/"RC2" inside unrelated identifiers.
                for algo, (cwe, desc) in self.WEAK_ALGORITHMS.items():
                    if re.search(rf"\b{re.escape(algo)}\b", line, re.IGNORECASE):
                        # Skip if it's a comment
                        stripped = line.strip()
                        if stripped.startswith(("#", "//", "/*", "*")):
                            continue

                        findings.append(
                            SASTFinding(
                                vulnerability_type=VulnerabilityType.WEAK_CRYPTO,
                                severity=Severity.HIGH,
                                title=f"Weak cryptographic algorithm: {algo}",
                                description=desc,
                                file_path=str(file_path),
                                line_number=i,
                                code_snippet=line.strip(),
                                recommendation=f"Replace {algo} with a stronger algorithm (AES-256, SHA-256, etc.)",
                                cwe_id=cwe,
                                owasp_category="M5: Insufficient Cryptography",
                            )
                        )

                # Check insecure random
                for pattern in self.INSECURE_RANDOM:
                    if pattern.lower() in lower_line:
                        findings.append(
                            SASTFinding(
                                vulnerability_type=VulnerabilityType.INSECURE_RANDOM,
                                severity=Severity.MEDIUM,
                                title="Insecure random number generator",
                                description=f"'{pattern}' is not cryptographically secure",
                                file_path=str(file_path),
                                line_number=i,
                                code_snippet=line.strip(),
                                recommendation="Use secrets module (Python), SecureRandom (Java), or SecRandomCopyBytes (iOS)",
                                cwe_id="CWE-338",
                            )
                        )

                # Check hardcoded keys
                for pattern in self.KEY_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(
                            SASTFinding(
                                vulnerability_type=VulnerabilityType.HARDCODED_KEY,
                                severity=Severity.CRITICAL,
                                title="Hardcoded cryptographic key",
                                description="Cryptographic key is hardcoded in source code",
                                file_path=str(file_path),
                                line_number=i,
                                code_snippet=line.strip()[:100],
                                recommendation="Store keys in secure key management systems or environment variables",
                                cwe_id="CWE-321",
                                owasp_category="M10: Insufficient Cryptography",
                            )
                        )

        except (OSError, UnicodeDecodeError) as e:
            # A file we can't read/decode is silently absent from the scan results.
            logger.debug("SAST crypto: skipped %s: %s", file_path, e)

        return findings
