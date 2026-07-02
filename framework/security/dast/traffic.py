"""Analyzer extracted from dast_analyzer (mechanical split; see dast/base.py)."""

import hashlib
import json
import re
import socket
import ssl
import subprocess
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

from framework.security.dast.base import (
    DASTTestType,
    DASTSeverity,
    NetworkRequest,
    DASTFinding,
    SSLAnalysisResult,
    DASTResult,
    APITestResult,
)


class NetworkTrafficAnalyzer:
    """
    Network Traffic Analyzer

    Intercepts and analyzes network traffic for security issues.
    """

    # Sensitive data patterns
    SENSITIVE_PATTERNS = {
        "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "api_key": r'\b(?:api[_-]?key|apikey|api_secret)["\s:=]+["\']?[\w\-]{20,}["\']?',
        "jwt": r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+",
        "password_in_url": r"[?&](?:password|passwd|pwd|pass)=([^&\s]+)",
        "bearer_token": r"Bearer\s+[\w\-\.]+",
    }

    def __init__(self):
        self.captured_requests: List[NetworkRequest] = []

    def analyze_request(self, request: NetworkRequest) -> List[DASTFinding]:
        """Analyze a network request for security issues"""
        findings = []

        # Check for cleartext transmission
        if not request.is_secure:
            findings.append(
                DASTFinding(
                    test_type=DASTTestType.NETWORK,
                    severity=DASTSeverity.HIGH,
                    title="Cleartext HTTP traffic",
                    description=f"Sensitive data transmitted over unencrypted HTTP to {request.url}",
                    evidence=f"HTTP request to {request.url}",
                    recommendation="Use HTTPS for all API communications",
                    request=request,
                    cwe_id="CWE-319",
                    owasp_category="M5: Insecure Communication",
                )
            )

        # Check for sensitive data in URL
        if request.method == "GET" and request.body:
            findings.extend(self._check_sensitive_in_url(request))

        # Check for sensitive data in request/response
        findings.extend(self._check_sensitive_data(request))

        # Check headers
        findings.extend(self._check_security_headers(request))

        self.captured_requests.append(request)
        return findings

    def _check_sensitive_in_url(self, request: NetworkRequest) -> List[DASTFinding]:
        """Check for sensitive data in URL"""
        findings = []

        parsed = urlparse(request.url)
        query = parsed.query

        sensitive_params = ["password", "passwd", "pwd", "secret", "token", "api_key", "apikey"]

        for param in sensitive_params:
            if param.lower() in query.lower():
                findings.append(
                    DASTFinding(
                        test_type=DASTTestType.DATA_EXPOSURE,
                        severity=DASTSeverity.HIGH,
                        title="Sensitive data in URL",
                        description=f"Parameter '{param}' found in URL query string",
                        evidence=f"URL contains {param} parameter",
                        recommendation="Send sensitive data in POST body or headers, not URL",
                        request=request,
                        cwe_id="CWE-598",
                    )
                )

        return findings

    def _check_sensitive_data(self, request: NetworkRequest) -> List[DASTFinding]:
        """Check for sensitive data exposure"""
        findings = []

        # Check request body
        if request.body:
            for name, pattern in self.SENSITIVE_PATTERNS.items():
                if re.search(pattern, request.body, re.IGNORECASE):
                    findings.append(
                        DASTFinding(
                            test_type=DASTTestType.DATA_EXPOSURE,
                            severity=DASTSeverity.MEDIUM,
                            title=f"Potential {name.replace('_', ' ')} in request",
                            description=f"Request body may contain {name.replace('_', ' ')}",
                            evidence=f"Pattern match for {name}",
                            recommendation=f"Verify if {name.replace('_', ' ')} needs to be transmitted",
                            request=request,
                            cwe_id="CWE-200",
                        )
                    )

        # Check response body
        if request.response_body:
            for name, pattern in self.SENSITIVE_PATTERNS.items():
                if re.search(pattern, request.response_body, re.IGNORECASE):
                    findings.append(
                        DASTFinding(
                            test_type=DASTTestType.DATA_EXPOSURE,
                            severity=DASTSeverity.HIGH,
                            title=f"Potential {name.replace('_', ' ')} in response",
                            description=f"Response contains potential {name.replace('_', ' ')}",
                            evidence=f"Pattern match for {name}",
                            recommendation="Remove or mask sensitive data in API responses",
                            request=request,
                            cwe_id="CWE-200",
                        )
                    )

        return findings

    def _check_security_headers(self, request: NetworkRequest) -> List[DASTFinding]:
        """Check response security headers"""
        findings = []

        # Required security headers
        required_headers = {
            "Strict-Transport-Security": ("HSTS not set", "CWE-319"),
            "X-Content-Type-Options": ("X-Content-Type-Options not set", "CWE-16"),
            "X-Frame-Options": ("X-Frame-Options not set (clickjacking risk)", "CWE-1021"),
            "Content-Security-Policy": ("CSP not set", "CWE-693"),
            "X-XSS-Protection": ("X-XSS-Protection not set", "CWE-79"),
        }

        response_headers = {k.lower(): v for k, v in request.headers.items()} if request.headers else {}

        for header, (message, cwe) in required_headers.items():
            if header.lower() not in response_headers:
                findings.append(
                    DASTFinding(
                        test_type=DASTTestType.NETWORK,
                        severity=DASTSeverity.MEDIUM,
                        title=f"Missing security header: {header}",
                        description=message,
                        evidence=f"Header {header} not present in response",
                        recommendation=f"Add {header} header to response",
                        request=request,
                        cwe_id=cwe,
                    )
                )

        return findings
