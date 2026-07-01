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


class SecureCodingAnalyzer:
    """
    Analyzes code for secure coding practices
    """

    def __init__(self):
        self.insecure_patterns = [
            # Insecure random
            (
                re.compile(r"Random\s*\(\s*\)|Math\.random|rand\(\)", re.I),
                "Insecure Random Number Generator",
                "Use SecureRandom/arc4random for security-sensitive operations",
                [330],
            ),
            # SQL Injection
            (
                re.compile(r"rawQuery\s*\([^)]*\+|execSQL\s*\([^)]*\+", re.I),
                "Potential SQL Injection",
                "Use parameterized queries instead of string concatenation",
                [89],
            ),
            # WebView JavaScript
            (
                re.compile(r"setJavaScriptEnabled\s*\(\s*true\s*\)", re.I),
                "WebView JavaScript Enabled",
                "Only enable JavaScript if necessary and validate all inputs",
                [79],
            ),
            # Insecure WebView
            (
                re.compile(r"setAllowFileAccess\s*\(\s*true\s*\)", re.I),
                "WebView File Access Enabled",
                "Disable file access in WebView unless absolutely necessary",
                [200],
            ),
            # Clipboard
            (
                re.compile(r"ClipboardManager|UIPasteboard", re.I),
                "Clipboard Usage Detected",
                "Avoid storing sensitive data in clipboard; it's accessible to other apps",
                [200],
            ),
            # World-readable/writable files
            (
                re.compile(r"MODE_WORLD_READABLE|MODE_WORLD_WRITEABLE", re.I),
                "World-Accessible File Mode",
                "Use MODE_PRIVATE for files containing sensitive data",
                [732],
            ),
            # Hardcoded IV
            (
                re.compile(r'IvParameterSpec\s*\(\s*["\'][^"\']+["\']\s*\.getBytes', re.I),
                "Hardcoded Initialization Vector",
                "Generate random IVs for each encryption operation",
                [329],
            ),
        ]

    def analyze(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Analyze source code for insecure practices"""
        vulnerabilities = []

        for ext in ["*.java", "*.kt", "*.swift", "*.m", "*.py", "*.js", "*.ts"]:
            for file_path in source_dir.rglob(ext):
                try:
                    content = file_path.read_text(errors="ignore")

                    for pattern, title, remediation, cwes in self.insecure_patterns:
                        for match in pattern.finditer(content):
                            line_num = content[: match.start()].count("\n") + 1

                            vulnerabilities.append(
                                SecurityVulnerability(
                                    id=f"CODE-{hashlib.md5(f'{file_path}:{line_num}:{title}'.encode()).hexdigest()[:8]}",
                                    title=title,
                                    description=f"Insecure coding practice detected: {title}",
                                    owasp_category=OWASPMobileTop10.M4_INSUFFICIENT_INPUT_OUTPUT,
                                    risk_level=RiskLevel.MEDIUM,
                                    cvss_score=5.5,
                                    cwe_ids=cwes,
                                    location=f"{file_path}:{line_num}",
                                    evidence=match.group(0)[:100],
                                    remediation=remediation,
                                    references=[],
                                )
                            )

                except Exception as e:
                    logger.warning(f"Could not analyze {file_path}: {e}")

        return vulnerabilities


# ============================================================================
# Advanced Security Scanner (Main Interface)
# ============================================================================
