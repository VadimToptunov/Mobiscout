"""Analyzer extracted from dast_analyzer (mechanical split; see dast/base.py)."""

import socket
import ssl
import time
import warnings
from typing import List

from framework.security.dast.base import (
    DASTTestType,
    DASTSeverity,
    DASTFinding,
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
        findings: List[DASTFinding] = []

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
        """Test for deprecated protocol support.

        Pins a *modern* client context (``PROTOCOL_TLS_CLIENT``) to one protocol
        version via ``minimum_version``/``maximum_version`` rather than the legacy
        ``PROTOCOL_TLSv1*`` constants. Those constants are deprecated-for-removal, and
        on OpenSSL 3.x a TLSv1-only context cannot complete *any* handshake (it fails
        locally with "internal error"), which the old code caught and read as "the
        server doesn't support it" — a permanent silent false negative for exactly the
        weakness this test exists to find. The legacy protocols also sit below the
        default security level, so the probe lowers it explicitly.
        """
        findings: List[DASTFinding] = []

        # (label, TLSVersion) — only versions this Python knows about. Naming a deprecated
        # version is the point of this test, so its DeprecationWarning is ours to silence
        # (it would otherwise fire on every scan); hasattr keeps us working if one is dropped.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            versions = [
                (name, getattr(ssl.TLSVersion, attr))
                for name, attr in (("TLSv1.0", "TLSv1"), ("TLSv1.1", "TLSv1_1"), ("TLSv1.2", "TLSv1_2"))
                if hasattr(ssl.TLSVersion, attr)
            ]

        for name, version in versions:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            try:
                # Legacy protocols/ciphers are refused at the default security level.
                context.set_ciphers("DEFAULT:@SECLEVEL=0")
            except ssl.SSLError:
                pass  # already permissive enough (or the stack won't lower it) — try anyway
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    context.minimum_version = version
                    context.maximum_version = version
            except (ValueError, OSError) as e:
                # This Python/OpenSSL cannot even *attempt* the version, so we learned
                # nothing about the server. Say so instead of silently passing.
                findings.append(
                    DASTFinding(
                        test_type=DASTTestType.SSL_TLS,
                        severity=DASTSeverity.INFO,
                        title=f"Could not test protocol: {name}",
                        description=(
                            f"The local TLS stack refused to negotiate {name}, so the server was not "
                            "tested for it. This is not evidence that the server rejects it."
                        ),
                        evidence=str(e),
                        recommendation=f"Re-test {name} with a TLS stack that still permits it (e.g. openssl s_client).",
                    )
                )
                continue

            try:
                with socket.create_connection((hostname, port), timeout=5) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        negotiated = ssock.version()
            except (ssl.SSLError, socket.error, OSError):
                continue  # server refused this version — good, for a deprecated one

            # Only report what was actually negotiated: a proxy or a server that ignores
            # our ceiling must not be recorded as "supports TLSv1.0".
            if negotiated != name.replace("TLSv1.0", "TLSv1") or name not in self.DEPRECATED_PROTOCOLS:
                continue
            findings.append(
                DASTFinding(
                    test_type=DASTTestType.SSL_TLS,
                    severity=DASTSeverity.HIGH if name in ["SSLv2", "SSLv3"] else DASTSeverity.MEDIUM,
                    title=f"Deprecated protocol supported: {name}",
                    description=f"Server supports {name} which is deprecated and insecure",
                    evidence=f"Successfully connected using {negotiated}",
                    recommendation=f"Disable {name} and use TLSv1.2 or TLSv1.3 only",
                    cwe_id="CWE-326",
                    owasp_category="M5: Insecure Communication",
                )
            )

        return findings

    def _test_ciphers(self, hostname: str, port: int) -> List[DASTFinding]:
        """Test for weak cipher suites"""
        findings: List[DASTFinding] = []

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
        findings: List[DASTFinding] = []

        try:
            context = ssl.create_default_context()

            with socket.create_connection((hostname, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()

                    if cert:
                        # Check expiration
                        not_after = ssl.cert_time_to_seconds(str(cert.get("notAfter", "")))
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
                        issuer = dict(x[0] for x in cert.get("issuer", []))  # type: ignore[misc]
                        subject = dict(x[0] for x in cert.get("subject", []))  # type: ignore[misc]

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
        findings: List[DASTFinding] = []

        # Test for HSTS header (requires HTTP connection)
        # This is a simplified check

        return findings
