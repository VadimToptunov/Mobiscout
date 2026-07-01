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


class PrivacyComplianceChecker:
    """
    Checks for privacy compliance issues (GDPR, CCPA)
    """

    def __init__(self):
        self.pii_patterns = {
            "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
            "phone": re.compile(r"\+?[1-9]\d{1,14}"),
            "ssn": re.compile(r"\d{3}-\d{2}-\d{4}"),
            "credit_card": re.compile(r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"),
            "ip_address": re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"),
        }

        self.tracking_patterns = [
            re.compile(r"google[_-]?analytics", re.I),
            re.compile(r"facebook[_-]?sdk", re.I),
            re.compile(r"firebase[_-]?analytics", re.I),
            re.compile(r"amplitude", re.I),
            re.compile(r"mixpanel", re.I),
            re.compile(r"appsflyer", re.I),
            re.compile(r"adjust\.com", re.I),
        ]

    def check_pii_logging(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Check for PII being logged"""
        vulnerabilities = []

        log_patterns = [
            re.compile(r"Log\.[divwe]\s*\([^)]*", re.I),
            re.compile(r"NSLog\s*\([^)]*", re.I),
            re.compile(r"print\s*\([^)]*", re.I),
            re.compile(r"console\.log\s*\([^)]*", re.I),
            re.compile(r"logger\.\w+\s*\([^)]*", re.I),
        ]

        for ext in ["*.java", "*.kt", "*.swift", "*.m", "*.py", "*.js", "*.ts"]:
            for file_path in source_dir.rglob(ext):
                try:
                    content = file_path.read_text(errors="ignore")

                    for log_pattern in log_patterns:
                        for match in log_pattern.finditer(content):
                            log_statement = match.group(0)

                            for pii_type, pii_pattern in self.pii_patterns.items():
                                if pii_pattern.search(log_statement):
                                    line_num = content[: match.start()].count("\n") + 1
                                    vulnerabilities.append(
                                        SecurityVulnerability(
                                            id=f"PRIVACY-LOG-{hashlib.md5(f'{file_path}:{line_num}'.encode()).hexdigest()[:8]}",
                                            title=f"PII ({pii_type}) Potentially Logged",
                                            description=f"A log statement may be logging {pii_type} data, "
                                            "which violates GDPR/CCPA requirements.",
                                            owasp_category=OWASPMobileTop10.M6_INADEQUATE_PRIVACY,
                                            risk_level=RiskLevel.HIGH,
                                            cvss_score=7.0,
                                            cwe_ids=[532],  # CWE-532: Insertion of Sensitive Info into Log
                                            location=f"{file_path}:{line_num}",
                                            evidence=f"Log statement: {log_statement[:100]}...",
                                            remediation="Remove PII from log statements or redact sensitive data.",
                                            references=["https://gdpr-info.eu/art-5-gdpr/"],
                                        )
                                    )

                except Exception as e:
                    logger.warning(f"Could not analyze {file_path}: {e}")

        return vulnerabilities

    def check_tracking_sdks(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Check for third-party tracking SDKs without consent"""
        vulnerabilities = []
        found_trackers = set()

        # Check Gradle files
        for gradle_file in source_dir.rglob("*.gradle*"):
            try:
                content = gradle_file.read_text(errors="ignore")
                for pattern in self.tracking_patterns:
                    if pattern.search(content):
                        found_trackers.add(pattern.pattern)
            except Exception:
                pass

        # Check Podfile
        podfile = source_dir / "Podfile"
        if podfile.exists():
            try:
                content = podfile.read_text()
                for pattern in self.tracking_patterns:
                    if pattern.search(content):
                        found_trackers.add(pattern.pattern)
            except Exception:
                pass

        if found_trackers:
            vulnerabilities.append(
                SecurityVulnerability(
                    id="PRIVACY-TRACKERS",
                    title="Third-Party Tracking SDKs Detected",
                    description=f"The app includes tracking SDKs: {', '.join(found_trackers)}. "
                    "Ensure proper user consent is obtained before tracking.",
                    owasp_category=OWASPMobileTop10.M6_INADEQUATE_PRIVACY,
                    risk_level=RiskLevel.MEDIUM,
                    cvss_score=5.0,
                    cwe_ids=[359],  # CWE-359: Privacy Violation
                    location="Dependencies",
                    evidence=f"Found trackers: {found_trackers}",
                    remediation="Implement consent management platform (CMP) and obtain "
                    "explicit user consent before enabling tracking.",
                    references=["https://gdpr-info.eu/art-7-gdpr/"],
                )
            )

        return vulnerabilities


# ============================================================================
# Root/Jailbreak Detection Analyzer
# ============================================================================
