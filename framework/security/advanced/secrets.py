"""Analyzer extracted from advanced_security (mechanical split; see advanced/base.py)."""

import hashlib
import logging
import re
from pathlib import Path
from typing import List, Optional

from framework.security import patterns
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

    def __init__(self) -> None:
        self.patterns = self._initialize_patterns()

    def _initialize_patterns(self) -> List[SecretPattern]:
        """Build the secret-detection patterns from the canonical spec list.

        The regex/severity/entropy data lives in ``framework.security.patterns``
        (``ADVANCED_SECRET_SPECS``); this maps the severity name onto the local
        ``RiskLevel`` enum so the shared module stays dependency-free.
        """
        risk_by_name = {level.name: level for level in RiskLevel}
        return [
            SecretPattern(name, regex, risk_by_name[severity], entropy)
            for name, regex, severity, entropy in patterns.ADVANCED_SECRET_SPECS
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
        """Check if match is likely a false positive.

        Delegates to the canonical helper in ``framework.security.patterns``:
        token indicators ("test", "demo", ...) are matched on word boundaries so
        an unrelated longer word ("latest", "manifest", "greatest") near a real
        secret does not suppress it. ``context`` is expected to be a narrow
        window around the match (see ``scan_content``), not a wide 200-char span.
        """
        return patterns.is_false_positive(match, context)

    def scan_content(self, content: str, filename: str = "unknown") -> List[SecurityVulnerability]:
        """Scan content for hardcoded secrets"""
        vulnerabilities = []

        for pattern in self.patterns:
            for match in pattern.pattern.finditer(content):
                matched_text = match.group(0)

                # Get a narrow surrounding context (a placeholder/test marker
                # only suppresses a secret when it is immediately adjacent, not
                # anywhere within a wide 200-char span).
                start = max(0, match.start() - 20)
                end = min(len(content), match.end() + 20)
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
            content = file_path.read_text(encoding="utf-8", errors="ignore")
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
