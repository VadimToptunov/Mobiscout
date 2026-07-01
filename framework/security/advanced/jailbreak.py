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


class RootJailbreakAnalyzer:
    """
    Analyzes root/jailbreak detection implementation
    """

    def __init__(self):
        self.android_root_checks = [
            re.compile(r"RootBeer|rootbeer", re.I),
            re.compile(r"isDeviceRooted|checkRoot|detectRoot", re.I),
            re.compile(r"su\s*binary|/system/xbin/su", re.I),
            re.compile(r"Superuser\.apk", re.I),
            re.compile(r"SafetyNet|safetynet", re.I),
        ]

        self.ios_jailbreak_checks = [
            re.compile(r"isJailbroken|checkJailbreak|detectJailbreak", re.I),
            re.compile(r"/Applications/Cydia\.app", re.I),
            re.compile(r"/Library/MobileSubstrate", re.I),
            re.compile(r"canOpenURL.*cydia", re.I),
        ]

    def analyze(self, source_dir: Path, platform: str = "android") -> List[SecurityVulnerability]:
        """Analyze root/jailbreak detection implementation"""
        vulnerabilities = []
        has_detection = False

        patterns = self.android_root_checks if platform == "android" else self.ios_jailbreak_checks
        extensions = ["*.java", "*.kt"] if platform == "android" else ["*.swift", "*.m"]

        for ext in extensions:
            for file_path in source_dir.rglob(ext):
                try:
                    content = file_path.read_text(errors="ignore")
                    if any(p.search(content) for p in patterns):
                        has_detection = True
                        break
                except Exception:
                    pass

        if not has_detection:
            term = "root" if platform == "android" else "jailbreak"
            vulnerabilities.append(
                SecurityVulnerability(
                    id=f"TAMPER-NO-{term.upper()}-DETECT",
                    title=f"No {term.capitalize()} Detection Implemented",
                    description=f"The app does not implement {term} detection. "
                    f"Running on {term}ed devices increases security risks.",
                    owasp_category=OWASPMobileTop10.M8_SECURITY_MISCONFIGURATION,
                    risk_level=RiskLevel.MEDIUM,
                    cvss_score=5.5,
                    cwe_ids=[919],  # CWE-919: Weaknesses in Mobile Applications
                    location="Application-wide",
                    evidence=f"No {term} detection patterns found",
                    remediation=f"Implement {term} detection and take appropriate action "
                    f"(warn user, restrict functionality, or exit).",
                    references=["https://owasp.org/www-project-mobile-top-10/2016-risks/m8-code-tampering"],
                )
            )

        return vulnerabilities


# ============================================================================
# Secure Coding Practice Analyzer
# ============================================================================
