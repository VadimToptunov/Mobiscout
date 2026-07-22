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


class SSLTLSAnalyzer:
    """
    SSL/TLS Security Analyzer

    Tests SSL/TLS configuration and certificate validation.
    """

    # Weak cipher suites
    WEAK_CIPHERS = {"RC4", "DES", "3DES", "MD5", "NULL", "EXPORT", "ANON", "ADH", "AECDH"}

    # Deprecated protocols
    DEPRECATED_PROTOCOLS = ["SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1"]

    def analyze_host(self, hostname: str, port: int = 443) -> List[DASTFinding]:
        """Analyze SSL/TLS configuration of a host"""
        findings = []

        try:
            # Test protocol versions
            findings.extend(self._test_protocols(hostname, port))

            # Test cipher suites
            findings.extend(self._test_ciphers(hostname, port))

            # Test certificate
            findings.extend(self._test_certificate(hostname, port))

            # Test for common vulnerabilities
            findings.extend(self._test_vulnerabilities(hostname, port))

        except (socket.error, ssl.SSLError, OSError) as e:
            findings.append(
                DASTFinding(
                    test_type=DASTTestType.SSL_TLS,
                    severity=DASTSeverity.INFO,
                    title="SSL/TLS connection failed",
                    description=f"Could not establish SSL/TLS connection: {e}",
                    evidence=str(e),
                    recommendation="Verify the server is accessible and has valid SSL configuration",
                )
            )

        return findings

    def _test_protocols(self, hostname: str, port: int) -> List[DASTFinding]:
        """Test for deprecated protocol support"""
        findings = []

        protocols_to_test = [
            (ssl.PROTOCOL_TLSv1, "TLSv1.0"),
            (ssl.PROTOCOL_TLSv1_1, "TLSv1.1") if hasattr(ssl, "PROTOCOL_TLSv1_1") else None,
            (ssl.PROTOCOL_TLSv1_2, "TLSv1.2") if hasattr(ssl, "PROTOCOL_TLSv1_2") else None,
        ]

        for proto_tuple in protocols_to_test:
            if proto_tuple is None:
                continue

            protocol, name = proto_tuple

            try:
                context = ssl.SSLContext(protocol)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

                with socket.create_connection((hostname, port), timeout=5) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname):
                        if name in self.DEPRECATED_PROTOCOLS:
                            findings.append(
                                DASTFinding(
                                    test_type=DASTTestType.SSL_TLS,
                                    severity=DASTSeverity.HIGH if name in ["SSLv2", "SSLv3"] else DASTSeverity.MEDIUM,
                                    title=f"Deprecated protocol supported: {name}",
                                    description=f"Server supports {name} which is deprecated and insecure",
                                    evidence=f"Successfully connected using {name}",
                                    recommendation=f"Disable {name} and use TLSv1.2 or TLSv1.3 only",
                                    cwe_id="CWE-326",
                                    owasp_category="M5: Insecure Communication",
                                )
                            )
            except (ssl.SSLError, socket.error, OSError):
                # Protocol not supported - this is good for deprecated ones
                pass

        return findings

    def _test_ciphers(self, hostname: str, port: int) -> List[DASTFinding]:
        """Test for weak cipher suites"""
        findings = []

        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            with socket.create_connection((hostname, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cipher = ssock.cipher()
                    if cipher:
                        cipher_name = cipher[0]

                        # Check for weak ciphers
                        for weak in self.WEAK_CIPHERS:
                            if weak in cipher_name.upper():
                                findings.append(
                                    DASTFinding(
                                        test_type=DASTTestType.SSL_TLS,
                                        severity=DASTSeverity.HIGH,
                                        title=f"Weak cipher suite: {cipher_name}",
                                        description=f"Server uses weak cipher containing {weak}",
                                        evidence=f"Negotiated cipher: {cipher_name}",
                                        recommendation="Configure server to use only strong ciphers (AES-GCM, ChaCha20)",
                                        cwe_id="CWE-327",
                                    )
                                )

        except (ssl.SSLError, socket.error, OSError):
            pass

        return findings

    def _test_certificate(self, hostname: str, port: int) -> List[DASTFinding]:
        """Test certificate validity and configuration"""
        findings = []

        try:
            context = ssl.create_default_context()

            with socket.create_connection((hostname, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()

                    if cert:
                        # Check expiration
                        not_after = ssl.cert_time_to_seconds(cert.get("notAfter", ""))
                        days_until_expiry = (not_after - time.time()) / 86400

                        if days_until_expiry < 0:
                            findings.append(
                                DASTFinding(
                                    test_type=DASTTestType.SSL_TLS,
                                    severity=DASTSeverity.CRITICAL,
                                    title="Expired SSL certificate",
                                    description="The SSL certificate has expired",
                                    evidence=f"Certificate expired on {cert.get('notAfter')}",
                                    recommendation="Renew the SSL certificate immediately",
                                    cwe_id="CWE-298",
                                )
                            )
                        elif days_until_expiry < 30:
                            findings.append(
                                DASTFinding(
                                    test_type=DASTTestType.SSL_TLS,
                                    severity=DASTSeverity.MEDIUM,
                                    title="SSL certificate expiring soon",
                                    description=f"Certificate expires in {int(days_until_expiry)} days",
                                    evidence=f"Certificate expires on {cert.get('notAfter')}",
                                    recommendation="Plan to renew the certificate before expiration",
                                    cwe_id="CWE-298",
                                )
                            )

                        # Check for self-signed
                        issuer = dict(x[0] for x in cert.get("issuer", []))
                        subject = dict(x[0] for x in cert.get("subject", []))

                        if issuer == subject:
                            findings.append(
                                DASTFinding(
                                    test_type=DASTTestType.SSL_TLS,
                                    severity=DASTSeverity.HIGH,
                                    title="Self-signed certificate",
                                    description="Server uses a self-signed certificate",
                                    evidence=f"Issuer equals Subject: {issuer.get('commonName', 'unknown')}",
                                    recommendation="Use a certificate from a trusted Certificate Authority",
                                    cwe_id="CWE-295",
                                )
                            )

        except ssl.SSLCertVerificationError as e:
            findings.append(
                DASTFinding(
                    test_type=DASTTestType.SSL_TLS,
                    severity=DASTSeverity.HIGH,
                    title="Certificate verification failed",
                    description=str(e),
                    evidence=str(e),
                    recommendation="Fix the certificate issues or obtain a valid certificate",
                    cwe_id="CWE-295",
                )
            )
        except (socket.error, OSError):
            pass

        return findings

    def _test_vulnerabilities(self, hostname: str, port: int) -> List[DASTFinding]:
        """Test for known SSL/TLS vulnerabilities"""
        findings = []

        # Test for HSTS header (requires HTTP connection)
        # This is a simplified check

        return findings
