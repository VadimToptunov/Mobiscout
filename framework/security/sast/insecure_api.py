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


class InsecureAPIAnalyzer:
    """
    Insecure API Usage Analyzer

    Detects usage of dangerous or deprecated APIs.
    """

    INSECURE_APIS = {
        # Python
        "eval(": ("CWE-95", Severity.CRITICAL, "Arbitrary code execution via eval()"),
        "exec(": ("CWE-95", Severity.CRITICAL, "Arbitrary code execution via exec()"),
        "compile(": ("CWE-95", Severity.HIGH, "Dynamic code compilation"),
        "pickle.load": ("CWE-502", Severity.HIGH, "Unsafe deserialization with pickle"),
        "yaml.load(": ("CWE-502", Severity.HIGH, "Unsafe YAML deserialization (use safe_load)"),
        "marshal.load": ("CWE-502", Severity.HIGH, "Unsafe deserialization with marshal"),
        "shelve.open": ("CWE-502", Severity.MEDIUM, "Shelve uses pickle internally"),
        "os.system(": ("CWE-78", Severity.HIGH, "Command injection risk with os.system"),
        "subprocess.call.*shell=True": ("CWE-78", Severity.HIGH, "Shell injection with shell=True"),
        "tempfile.mktemp": ("CWE-377", Severity.MEDIUM, "Race condition in temp file creation"),
        "assert ": ("CWE-617", Severity.LOW, "Assert can be disabled in production"),
        # Android/Java
        "setJavaScriptEnabled(true)": ("CWE-79", Severity.HIGH, "JavaScript enabled in WebView"),
        "setAllowFileAccess(true)": ("CWE-200", Severity.HIGH, "File access enabled in WebView"),
        "addJavascriptInterface": ("CWE-749", Severity.CRITICAL, "JavaScript interface injection risk"),
        "MODE_WORLD_READABLE": ("CWE-732", Severity.HIGH, "World-readable file permissions"),
        "MODE_WORLD_WRITEABLE": ("CWE-732", Severity.CRITICAL, "World-writable file permissions"),
        'allowBackup="true"': ("CWE-530", Severity.MEDIUM, "App backup enabled"),
        'debuggable="true"': ("CWE-489", Severity.CRITICAL, "Debug mode enabled"),
        'usesCleartextTraffic="true"': ("CWE-319", Severity.HIGH, "Cleartext traffic allowed"),
        "TrustManager": ("CWE-295", Severity.HIGH, "Custom TrustManager may bypass cert validation"),
        "X509TrustManager": ("CWE-295", Severity.HIGH, "Custom X509TrustManager detected"),
        "HostnameVerifier": ("CWE-297", Severity.HIGH, "Custom HostnameVerifier detected"),
        "ALLOW_ALL_HOSTNAME_VERIFIER": ("CWE-297", Severity.CRITICAL, "All hostnames accepted"),
        # iOS/Swift
        "NSAllowsArbitraryLoads": ("CWE-319", Severity.HIGH, "ATS disabled - cleartext allowed"),
        "allowsInvalidSSLCertificate": ("CWE-295", Severity.CRITICAL, "Invalid SSL certificates allowed"),
        "SecTrustSetAnchorCertificates": ("CWE-295", Severity.MEDIUM, "Custom trust anchor"),
        "kSecAttrAccessibleAlways": ("CWE-311", Severity.HIGH, "Keychain item always accessible"),
        "evaluateJavaScript": ("CWE-79", Severity.MEDIUM, "JavaScript evaluation in WebView"),
    }

    def analyze(self, file_path: Path) -> List[SASTFinding]:
        """Analyze file for insecure API usage"""
        findings = []

        try:
            content = file_path.read_text()
            lines = content.splitlines()

            for i, line in enumerate(lines, 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith(("#", "//", "/*", "*", '"""', "'''")):
                    continue

                for pattern, (cwe, severity, desc) in self.INSECURE_APIS.items():
                    # Use simple string matching for patterns without regex special chars
                    # or regex for patterns with wildcards
                    matched = False
                    if "*" in pattern or "?" in pattern or "[" in pattern:
                        # Escape parentheses for regex matching
                        escaped_pattern = pattern.replace("(", r"\(").replace(")", r"\)")
                        try:
                            matched = bool(re.search(escaped_pattern, line))
                        except re.error:
                            matched = pattern in line
                    else:
                        # Simple substring match
                        matched = pattern in line

                    if matched:
                        findings.append(
                            SASTFinding(
                                vulnerability_type=(
                                    VulnerabilityType.INSECURE_WEBVIEW
                                    if "WebView" in desc or "JavaScript" in desc
                                    else VulnerabilityType.COMMAND_INJECTION
                                ),
                                severity=severity,
                                title=f"Insecure API usage: {pattern.split('(')[0] if '(' in pattern else pattern}",
                                description=desc,
                                file_path=str(file_path),
                                line_number=i,
                                code_snippet=line.strip(),
                                cwe_id=cwe,
                            )
                        )

        except (OSError, UnicodeDecodeError) as e:
            logger.debug("SAST insecure-api: skipped %s: %s", file_path, e)

        return findings
