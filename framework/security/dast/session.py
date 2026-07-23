"""Analyzer extracted from dast_analyzer (mechanical split; see dast/base.py)."""

from typing import Dict, List

from framework.security.dast.base import (
    DASTTestType,
    DASTSeverity,
    DASTFinding,
)


class SessionAnalyzer:
    """
    Session Management Analyzer

    Tests session handling and authentication.
    """

    def analyze_session(self, session_token: str, cookies: Dict[str, str]) -> List[DASTFinding]:
        """Analyze session security"""
        findings: List[DASTFinding] = []

        # Analyze token strength
        findings.extend(self._analyze_token_strength(session_token))

        # Analyze cookie security
        findings.extend(self._analyze_cookies(cookies))

        return findings

    def _analyze_token_strength(self, token: str) -> List[DASTFinding]:
        """Analyze session token strength"""
        findings: List[DASTFinding] = []

        # Check token length
        if len(token) < 32:
            findings.append(
                DASTFinding(
                    test_type=DASTTestType.SESSION,
                    severity=DASTSeverity.MEDIUM,
                    title="Weak session token",
                    description=f"Session token is only {len(token)} characters",
                    evidence=f"Token length: {len(token)}",
                    recommendation="Use tokens of at least 128 bits (32 hex characters)",
                    cwe_id="CWE-330",
                )
            )

        # Check for sequential tokens
        if token.isdigit():
            findings.append(
                DASTFinding(
                    test_type=DASTTestType.SESSION,
                    severity=DASTSeverity.HIGH,
                    title="Predictable session token",
                    description="Session token appears to be numeric/sequential",
                    evidence="Token consists only of digits",
                    recommendation="Use cryptographically secure random token generation",
                    cwe_id="CWE-330",
                )
            )

        # Check entropy
        unique_chars = len(set(token))
        if unique_chars < len(token) * 0.4:
            findings.append(
                DASTFinding(
                    test_type=DASTTestType.SESSION,
                    severity=DASTSeverity.MEDIUM,
                    title="Low entropy session token",
                    description="Session token has low character diversity",
                    evidence=f"Only {unique_chars} unique characters in {len(token)} length token",
                    recommendation="Use cryptographically secure random token generation",
                    cwe_id="CWE-330",
                )
            )

        return findings

    def _analyze_cookies(self, cookies: Dict[str, str]) -> List[DASTFinding]:
        """Analyze cookie security attributes"""
        findings: List[DASTFinding] = []

        # Note: In real implementation, you'd parse actual cookie headers
        # with all attributes (Secure, HttpOnly, SameSite, etc.)

        return findings
