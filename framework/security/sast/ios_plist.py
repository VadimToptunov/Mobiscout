"""Analyzer extracted from sast_analyzer (mechanical split; see sast/base.py)."""

import logging
from pathlib import Path
from typing import List

from framework.security.sast.base import (
    VulnerabilityType,
    Severity,
    SASTFinding,
)

logger = logging.getLogger(__name__)


class IOSPlistAnalyzer:
    """
    iOS Info.plist Security Analyzer

    Analyzes Info.plist for security issues.
    """

    def analyze(self, plist_path: Path) -> List[SASTFinding]:
        """Analyze Info.plist"""
        findings = []

        try:
            import plistlib

            with open(plist_path, "rb") as f:
                plist = plistlib.load(f)

            # Check ATS settings
            ats = plist.get("NSAppTransportSecurity", {})

            if ats.get("NSAllowsArbitraryLoads", False):
                findings.append(
                    SASTFinding(
                        vulnerability_type=VulnerabilityType.CLEARTEXT_TRANSMISSION,
                        severity=Severity.HIGH,
                        title="App Transport Security disabled",
                        description="NSAllowsArbitraryLoads allows cleartext HTTP traffic",
                        file_path=str(plist_path),
                        line_number=1,
                        recommendation="Remove NSAllowsArbitraryLoads and use HTTPS",
                        cwe_id="CWE-319",
                        owasp_category="M5: Insecure Communication",
                    )
                )

            # Check URL schemes
            url_types = plist.get("CFBundleURLTypes", [])
            for url_type in url_types:
                schemes = url_type.get("CFBundleURLSchemes", [])
                for scheme in schemes:
                    if scheme not in ["http", "https"]:
                        findings.append(
                            SASTFinding(
                                vulnerability_type=VulnerabilityType.INSECURE_DEEP_LINK,
                                severity=Severity.INFO,
                                title=f"Custom URL scheme: {scheme}",
                                description="Custom URL schemes should validate input carefully",
                                file_path=str(plist_path),
                                line_number=1,
                                recommendation="Validate all data received via URL scheme",
                                cwe_id="CWE-939",
                            )
                        )

            # Check background modes
            background_modes = plist.get("UIBackgroundModes", [])
            if "fetch" in background_modes or "remote-notification" in background_modes:
                findings.append(
                    SASTFinding(
                        vulnerability_type=VulnerabilityType.CLIPBOARD_DATA,
                        severity=Severity.INFO,
                        title="Background execution enabled",
                        description=f"App can execute in background: {background_modes}",
                        file_path=str(plist_path),
                        line_number=1,
                        recommendation="Ensure background tasks handle sensitive data securely",
                        cwe_id="CWE-200",
                    )
                )

        except Exception as e:
            # Broad by design (a malformed plist must not abort the scan), but a
            # skipped Info.plist leaves its ATS/URL-scheme issues unaudited.
            logger.debug("SAST ios-plist: skipped %s: %s", plist_path, e)

        return findings
