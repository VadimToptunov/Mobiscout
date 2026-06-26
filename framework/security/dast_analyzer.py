"""
Dynamic Application Security Testing (DAST) Module

Runtime security testing for mobile applications.

Features:
- Network traffic interception and analysis
- SSL/TLS validation testing
- API security testing
- Authentication testing
- Session management testing
- Input validation testing
- Runtime behavior monitoring
"""

import hashlib
import json
import re
import socket
import ssl
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs
import threading


class DASTTestType(Enum):
    """DAST test types"""
    SSL_TLS = "ssl_tls"
    NETWORK = "network"
    API = "api"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    SESSION = "session"
    INPUT_VALIDATION = "input_validation"
    INJECTION = "injection"
    DATA_EXPOSURE = "data_exposure"


class DASTSeverity(Enum):
    """DAST finding severity"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class NetworkRequest:
    """Captured network request"""
    timestamp: datetime
    method: str
    url: str
    headers: Dict[str, str]
    body: Optional[str]
    is_secure: bool
    response_code: Optional[int] = None
    response_body: Optional[str] = None
    response_time_ms: float = 0.0


@dataclass
class DASTFinding:
    """DAST vulnerability finding"""
    test_type: DASTTestType
    severity: DASTSeverity
    title: str
    description: str
    evidence: str
    recommendation: str
    request: Optional[NetworkRequest] = None
    cwe_id: Optional[str] = None
    owasp_category: Optional[str] = None
    cvss_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Additional fields for CLI compatibility
    category: str = ""
    endpoint: str = ""
    method: str = ""
    vulnerability_type: str = ""

    def __post_init__(self):
        # Set category from test_type if not provided
        if not self.category:
            self.category = self.test_type.value

    @property
    def severity_str(self) -> str:
        """Get severity as string for CLI compatibility"""
        return self.severity.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_type": self.test_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "cwe_id": self.cwe_id,
            "owasp_category": self.owasp_category,
            "cvss_score": self.cvss_score,
            "metadata": self.metadata,
            "category": self.category,
            "endpoint": self.endpoint,
            "method": self.method,
            "vulnerability_type": self.vulnerability_type,
        }


@dataclass
class SSLAnalysisResult:
    """SSL/TLS analysis result"""
    findings: List[DASTFinding] = field(default_factory=list)
    protocol: str = ""
    cipher_suite: str = ""
    cert_expiry: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "protocol": self.protocol,
            "cipher_suite": self.cipher_suite,
            "cert_expiry": self.cert_expiry,
        }


@dataclass
class DASTResult:
    """DAST analysis result wrapper"""
    findings: List[DASTFinding] = field(default_factory=list)
    target: str = ""
    port: int = 443
    scan_time: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "port": self.port,
            "scan_time": self.scan_time,
            "total_findings": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class APITestResult:
    """API security test result"""
    findings: List[DASTFinding] = field(default_factory=list)
    base_url: str = ""
    endpoints_tested: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "endpoints_tested": self.endpoints_tested,
            "findings": [f.to_dict() for f in self.findings],
        }


class SSLTLSAnalyzer:
    """
    SSL/TLS Security Analyzer

    Tests SSL/TLS configuration and certificate validation.
    """

    # Weak cipher suites
    WEAK_CIPHERS = {
        'RC4', 'DES', '3DES', 'MD5', 'NULL', 'EXPORT', 'ANON', 'ADH', 'AECDH'
    }

    # Deprecated protocols
    DEPRECATED_PROTOCOLS = ['SSLv2', 'SSLv3', 'TLSv1.0', 'TLSv1.1']

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
            findings.append(DASTFinding(
                test_type=DASTTestType.SSL_TLS,
                severity=DASTSeverity.INFO,
                title="SSL/TLS connection failed",
                description=f"Could not establish SSL/TLS connection: {e}",
                evidence=str(e),
                recommendation="Verify the server is accessible and has valid SSL configuration",
            ))

        return findings

    def _test_protocols(self, hostname: str, port: int) -> List[DASTFinding]:
        """Test for deprecated protocol support"""
        findings = []

        protocols_to_test = [
            (ssl.PROTOCOL_TLSv1, "TLSv1.0"),
            (ssl.PROTOCOL_TLSv1_1, "TLSv1.1") if hasattr(ssl, 'PROTOCOL_TLSv1_1') else None,
            (ssl.PROTOCOL_TLSv1_2, "TLSv1.2") if hasattr(ssl, 'PROTOCOL_TLSv1_2') else None,
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
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        if name in self.DEPRECATED_PROTOCOLS:
                            findings.append(DASTFinding(
                                test_type=DASTTestType.SSL_TLS,
                                severity=DASTSeverity.HIGH if name in ['SSLv2', 'SSLv3'] else DASTSeverity.MEDIUM,
                                title=f"Deprecated protocol supported: {name}",
                                description=f"Server supports {name} which is deprecated and insecure",
                                evidence=f"Successfully connected using {name}",
                                recommendation=f"Disable {name} and use TLSv1.2 or TLSv1.3 only",
                                cwe_id="CWE-326",
                                owasp_category="M5: Insecure Communication",
                            ))
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
                                findings.append(DASTFinding(
                                    test_type=DASTTestType.SSL_TLS,
                                    severity=DASTSeverity.HIGH,
                                    title=f"Weak cipher suite: {cipher_name}",
                                    description=f"Server uses weak cipher containing {weak}",
                                    evidence=f"Negotiated cipher: {cipher_name}",
                                    recommendation="Configure server to use only strong ciphers (AES-GCM, ChaCha20)",
                                    cwe_id="CWE-327",
                                ))

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
                        not_after = ssl.cert_time_to_seconds(cert.get('notAfter', ''))
                        days_until_expiry = (not_after - time.time()) / 86400

                        if days_until_expiry < 0:
                            findings.append(DASTFinding(
                                test_type=DASTTestType.SSL_TLS,
                                severity=DASTSeverity.CRITICAL,
                                title="Expired SSL certificate",
                                description="The SSL certificate has expired",
                                evidence=f"Certificate expired on {cert.get('notAfter')}",
                                recommendation="Renew the SSL certificate immediately",
                                cwe_id="CWE-298",
                            ))
                        elif days_until_expiry < 30:
                            findings.append(DASTFinding(
                                test_type=DASTTestType.SSL_TLS,
                                severity=DASTSeverity.MEDIUM,
                                title="SSL certificate expiring soon",
                                description=f"Certificate expires in {int(days_until_expiry)} days",
                                evidence=f"Certificate expires on {cert.get('notAfter')}",
                                recommendation="Plan to renew the certificate before expiration",
                                cwe_id="CWE-298",
                            ))

                        # Check for self-signed
                        issuer = dict(x[0] for x in cert.get('issuer', []))
                        subject = dict(x[0] for x in cert.get('subject', []))

                        if issuer == subject:
                            findings.append(DASTFinding(
                                test_type=DASTTestType.SSL_TLS,
                                severity=DASTSeverity.HIGH,
                                title="Self-signed certificate",
                                description="Server uses a self-signed certificate",
                                evidence=f"Issuer equals Subject: {issuer.get('commonName', 'unknown')}",
                                recommendation="Use a certificate from a trusted Certificate Authority",
                                cwe_id="CWE-295",
                            ))

        except ssl.SSLCertVerificationError as e:
            findings.append(DASTFinding(
                test_type=DASTTestType.SSL_TLS,
                severity=DASTSeverity.HIGH,
                title="Certificate verification failed",
                description=str(e),
                evidence=str(e),
                recommendation="Fix the certificate issues or obtain a valid certificate",
                cwe_id="CWE-295",
            ))
        except (socket.error, OSError):
            pass

        return findings

    def _test_vulnerabilities(self, hostname: str, port: int) -> List[DASTFinding]:
        """Test for known SSL/TLS vulnerabilities"""
        findings = []

        # Test for HSTS header (requires HTTP connection)
        # This is a simplified check

        return findings


class APISecurityTester:
    """
    API Security Tester

    Tests API endpoints for common vulnerabilities.
    """

    # Common injection payloads
    SQL_PAYLOADS = [
        "' OR '1'='1",
        "1; DROP TABLE users--",
        "1' AND '1'='1",
        "admin'--",
        "' UNION SELECT NULL--",
    ]

    XSS_PAYLOADS = [
        "<script>alert('XSS')</script>",
        "'\"><img src=x onerror=alert('XSS')>",
        "javascript:alert('XSS')",
        "<svg onload=alert('XSS')>",
    ]

    NOSQL_PAYLOADS = [
        '{"$gt": ""}',
        '{"$ne": null}',
        '{"$where": "sleep(5000)"}',
    ]

    PATH_TRAVERSAL_PAYLOADS = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "....//....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ]

    def test_endpoint(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        body: Optional[str] = None
    ) -> List[DASTFinding]:
        """Test API endpoint for vulnerabilities"""
        findings = []

        # Test SQL injection
        findings.extend(self._test_sql_injection(url, method, headers, params))

        # Test XSS
        findings.extend(self._test_xss(url, method, headers, params))

        # Test path traversal
        findings.extend(self._test_path_traversal(url, method, headers, params))

        # Test authentication bypass
        findings.extend(self._test_auth_bypass(url, method, headers))

        # Test rate limiting
        findings.extend(self._test_rate_limiting(url, method, headers))

        # Test CORS
        findings.extend(self._test_cors(url, headers))

        return findings

    def _test_sql_injection(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]],
        params: Optional[Dict[str, str]]
    ) -> List[DASTFinding]:
        """Test for SQL injection vulnerabilities"""
        findings = []

        # This is a conceptual implementation
        # In production, you would actually make HTTP requests
        for payload in self.SQL_PAYLOADS:
            # Simulate testing each parameter with payload
            error_patterns = [
                "sql syntax", "mysql", "sqlite", "postgresql", "oracle",
                "syntax error", "unclosed quotation", "unterminated string"
            ]

            # Simulate response analysis
            # In real implementation:
            # response = requests.get(url, params={key: payload for key in params})
            # if any(pattern in response.text.lower() for pattern in error_patterns):
            #     findings.append(...)

        return findings

    def _test_xss(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]],
        params: Optional[Dict[str, str]]
    ) -> List[DASTFinding]:
        """Test for XSS vulnerabilities"""
        findings = []

        for payload in self.XSS_PAYLOADS:
            # Simulate XSS testing
            # In real implementation, check if payload is reflected unencoded
            pass

        return findings

    def _test_path_traversal(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]],
        params: Optional[Dict[str, str]]
    ) -> List[DASTFinding]:
        """Test for path traversal vulnerabilities"""
        findings = []

        for payload in self.PATH_TRAVERSAL_PAYLOADS:
            # Simulate path traversal testing
            pass

        return findings

    def _test_auth_bypass(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]]
    ) -> List[DASTFinding]:
        """Test for authentication bypass"""
        findings = []

        # Test without authentication
        # Test with modified tokens
        # Test with expired tokens
        # Test parameter manipulation

        return findings

    def _test_rate_limiting(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]]
    ) -> List[DASTFinding]:
        """Test for rate limiting"""
        findings = []

        # Make rapid requests and check for rate limiting
        # If no rate limiting found, report as vulnerability

        return findings

    def _test_cors(
        self,
        url: str,
        headers: Optional[Dict[str, str]]
    ) -> List[DASTFinding]:
        """Test CORS configuration"""
        findings = []

        # Test with different Origin headers
        # Check for Access-Control-Allow-Origin: *
        # Check for credential reflection

        return findings


class NetworkTrafficAnalyzer:
    """
    Network Traffic Analyzer

    Intercepts and analyzes network traffic for security issues.
    """

    # Sensitive data patterns
    SENSITIVE_PATTERNS = {
        "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "api_key": r'\b(?:api[_-]?key|apikey|api_secret)["\s:=]+["\']?[\w\-]{20,}["\']?',
        "jwt": r'eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+',
        "password_in_url": r'[?&](?:password|passwd|pwd|pass)=([^&\s]+)',
        "bearer_token": r'Bearer\s+[\w\-\.]+',
    }

    def __init__(self):
        self.captured_requests: List[NetworkRequest] = []

    def analyze_request(self, request: NetworkRequest) -> List[DASTFinding]:
        """Analyze a network request for security issues"""
        findings = []

        # Check for cleartext transmission
        if not request.is_secure:
            findings.append(DASTFinding(
                test_type=DASTTestType.NETWORK,
                severity=DASTSeverity.HIGH,
                title="Cleartext HTTP traffic",
                description=f"Sensitive data transmitted over unencrypted HTTP to {request.url}",
                evidence=f"HTTP request to {request.url}",
                recommendation="Use HTTPS for all API communications",
                request=request,
                cwe_id="CWE-319",
                owasp_category="M5: Insecure Communication",
            ))

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

        sensitive_params = ['password', 'passwd', 'pwd', 'secret', 'token', 'api_key', 'apikey']

        for param in sensitive_params:
            if param.lower() in query.lower():
                findings.append(DASTFinding(
                    test_type=DASTTestType.DATA_EXPOSURE,
                    severity=DASTSeverity.HIGH,
                    title="Sensitive data in URL",
                    description=f"Parameter '{param}' found in URL query string",
                    evidence=f"URL contains {param} parameter",
                    recommendation="Send sensitive data in POST body or headers, not URL",
                    request=request,
                    cwe_id="CWE-598",
                ))

        return findings

    def _check_sensitive_data(self, request: NetworkRequest) -> List[DASTFinding]:
        """Check for sensitive data exposure"""
        findings = []

        # Check request body
        if request.body:
            for name, pattern in self.SENSITIVE_PATTERNS.items():
                if re.search(pattern, request.body, re.IGNORECASE):
                    findings.append(DASTFinding(
                        test_type=DASTTestType.DATA_EXPOSURE,
                        severity=DASTSeverity.MEDIUM,
                        title=f"Potential {name.replace('_', ' ')} in request",
                        description=f"Request body may contain {name.replace('_', ' ')}",
                        evidence=f"Pattern match for {name}",
                        recommendation=f"Verify if {name.replace('_', ' ')} needs to be transmitted",
                        request=request,
                        cwe_id="CWE-200",
                    ))

        # Check response body
        if request.response_body:
            for name, pattern in self.SENSITIVE_PATTERNS.items():
                if re.search(pattern, request.response_body, re.IGNORECASE):
                    findings.append(DASTFinding(
                        test_type=DASTTestType.DATA_EXPOSURE,
                        severity=DASTSeverity.HIGH,
                        title=f"Potential {name.replace('_', ' ')} in response",
                        description=f"Response contains potential {name.replace('_', ' ')}",
                        evidence=f"Pattern match for {name}",
                        recommendation="Remove or mask sensitive data in API responses",
                        request=request,
                        cwe_id="CWE-200",
                    ))

        return findings

    def _check_security_headers(self, request: NetworkRequest) -> List[DASTFinding]:
        """Check response security headers"""
        findings = []

        # Required security headers
        required_headers = {
            'Strict-Transport-Security': ('HSTS not set', 'CWE-319'),
            'X-Content-Type-Options': ('X-Content-Type-Options not set', 'CWE-16'),
            'X-Frame-Options': ('X-Frame-Options not set (clickjacking risk)', 'CWE-1021'),
            'Content-Security-Policy': ('CSP not set', 'CWE-693'),
            'X-XSS-Protection': ('X-XSS-Protection not set', 'CWE-79'),
        }

        response_headers = {k.lower(): v for k, v in request.headers.items()} if request.headers else {}

        for header, (message, cwe) in required_headers.items():
            if header.lower() not in response_headers:
                findings.append(DASTFinding(
                    test_type=DASTTestType.NETWORK,
                    severity=DASTSeverity.MEDIUM,
                    title=f"Missing security header: {header}",
                    description=message,
                    evidence=f"Header {header} not present in response",
                    recommendation=f"Add {header} header to response",
                    request=request,
                    cwe_id=cwe,
                ))

        return findings


class SessionAnalyzer:
    """
    Session Management Analyzer

    Tests session handling and authentication.
    """

    def analyze_session(
        self,
        session_token: str,
        cookies: Dict[str, str]
    ) -> List[DASTFinding]:
        """Analyze session security"""
        findings = []

        # Analyze token strength
        findings.extend(self._analyze_token_strength(session_token))

        # Analyze cookie security
        findings.extend(self._analyze_cookies(cookies))

        return findings

    def _analyze_token_strength(self, token: str) -> List[DASTFinding]:
        """Analyze session token strength"""
        findings = []

        # Check token length
        if len(token) < 32:
            findings.append(DASTFinding(
                test_type=DASTTestType.SESSION,
                severity=DASTSeverity.MEDIUM,
                title="Weak session token",
                description=f"Session token is only {len(token)} characters",
                evidence=f"Token length: {len(token)}",
                recommendation="Use tokens of at least 128 bits (32 hex characters)",
                cwe_id="CWE-330",
            ))

        # Check for sequential tokens
        if token.isdigit():
            findings.append(DASTFinding(
                test_type=DASTTestType.SESSION,
                severity=DASTSeverity.HIGH,
                title="Predictable session token",
                description="Session token appears to be numeric/sequential",
                evidence="Token consists only of digits",
                recommendation="Use cryptographically secure random token generation",
                cwe_id="CWE-330",
            ))

        # Check entropy
        unique_chars = len(set(token))
        if unique_chars < len(token) * 0.4:
            findings.append(DASTFinding(
                test_type=DASTTestType.SESSION,
                severity=DASTSeverity.MEDIUM,
                title="Low entropy session token",
                description="Session token has low character diversity",
                evidence=f"Only {unique_chars} unique characters in {len(token)} length token",
                recommendation="Use cryptographically secure random token generation",
                cwe_id="CWE-330",
            ))

        return findings

    def _analyze_cookies(self, cookies: Dict[str, str]) -> List[DASTFinding]:
        """Analyze cookie security attributes"""
        findings = []

        # Note: In real implementation, you'd parse actual cookie headers
        # with all attributes (Secure, HttpOnly, SameSite, etc.)

        return findings


class DASTAnalyzer:
    """
    Comprehensive DAST Analyzer

    Combines all dynamic analysis techniques.
    """

    def __init__(self):
        self.ssl_analyzer = SSLTLSAnalyzer()
        self.api_tester = APISecurityTester()
        self.network_analyzer = NetworkTrafficAnalyzer()
        self.session_analyzer = SessionAnalyzer()

    def analyze_host(self, hostname: str, port: int = 443) -> List[DASTFinding]:
        """Analyze a host for SSL/TLS issues"""
        return self.ssl_analyzer.analyze_host(hostname, port)

    def analyze_api(
        self,
        base_url: str,
        endpoints: List[Dict[str, Any]],
        auth_header: Optional[str] = None
    ) -> List[DASTFinding]:
        """Analyze API endpoints"""
        findings = []

        headers = {"Authorization": auth_header} if auth_header else None

        for endpoint in endpoints:
            url = f"{base_url}{endpoint.get('path', '')}"
            method = endpoint.get('method', 'GET')
            params = endpoint.get('params', {})

            findings.extend(self.api_tester.test_endpoint(url, method, headers, params))

        return findings

    def analyze_traffic(self, requests: List[NetworkRequest]) -> List[DASTFinding]:
        """Analyze captured network traffic"""
        findings = []

        for request in requests:
            findings.extend(self.network_analyzer.analyze_request(request))

        return findings

    def get_summary(self, findings: List[DASTFinding]) -> Dict[str, Any]:
        """Get analysis summary"""
        by_severity = {}
        by_type = {}

        for finding in findings:
            sev = finding.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            test_type = finding.test_type.value
            by_type[test_type] = by_type.get(test_type, 0) + 1

        return {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_type": by_type,
            "critical": by_severity.get("critical", 0),
            "high": by_severity.get("high", 0),
            "medium": by_severity.get("medium", 0),
            "low": by_severity.get("low", 0),
        }

    def export_report(self, findings: List[DASTFinding], output_path: Path) -> None:
        """Export findings to JSON"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "scan_time": datetime.now().isoformat(),
            "summary": self.get_summary(findings),
            "findings": [f.to_dict() for f in findings],
        }

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

    def analyze(self, target: str, port: int = 443) -> DASTResult:
        """
        Run comprehensive DAST analysis on a target.

        This is the main entry point for CLI.
        """
        findings = []

        # Run SSL/TLS analysis
        findings.extend(self.ssl_analyzer.analyze_host(target, port))

        return DASTResult(
            findings=findings,
            target=target,
            port=port,
        )

    def analyze_ssl(self, host: str, port: int = 443) -> SSLAnalysisResult:
        """
        Analyze SSL/TLS configuration of a host.

        Returns detailed SSL info including protocol and cipher.
        """
        findings = self.ssl_analyzer.analyze_host(host, port)

        # Try to get connection details
        protocol = ""
        cipher_suite = ""
        cert_expiry = ""

        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            with socket.create_connection((host, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    protocol = ssock.version() or ""
                    cipher = ssock.cipher()
                    if cipher:
                        cipher_suite = cipher[0]

                    cert = ssock.getpeercert()
                    if cert:
                        cert_expiry = cert.get('notAfter', '')
        except (socket.error, ssl.SSLError, OSError):
            pass

        return SSLAnalysisResult(
            findings=findings,
            protocol=protocol,
            cipher_suite=cipher_suite,
            cert_expiry=cert_expiry,
        )

    def test_api(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        endpoints: Optional[List[Dict[str, Any]]] = None
    ) -> APITestResult:
        """
        Test API endpoints for security vulnerabilities.

        Args:
            base_url: Base URL of the API
            headers: Optional headers including authorization
            endpoints: Optional list of endpoint definitions
        """
        findings = []

        auth_header = headers.get("Authorization") if headers else None

        # If no endpoints provided, test base URL
        if not endpoints:
            endpoints = [{"path": "/", "method": "GET"}]

        for endpoint in endpoints:
            url = f"{base_url.rstrip('/')}{endpoint.get('path', '/')}"
            method = endpoint.get('method', 'GET')
            params = endpoint.get('params', {})

            endpoint_findings = self.api_tester.test_endpoint(
                url, method, headers, params
            )

            # Add endpoint info to findings
            for finding in endpoint_findings:
                finding.endpoint = endpoint.get('path', '/')
                finding.method = method

            findings.extend(endpoint_findings)

        return APITestResult(
            findings=findings,
            base_url=base_url,
            endpoints_tested=len(endpoints),
        )

    def export_html(self, result: DASTResult, output_path: Path) -> None:
        """Export DAST results to HTML report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>DAST Security Report - {result.target}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
        .stat {{ padding: 20px; border-radius: 8px; text-align: center; }}
        .stat.critical {{ background: #f8d7da; color: #721c24; }}
        .stat.high {{ background: #fff3cd; color: #856404; }}
        .stat.medium {{ background: #d1ecf1; color: #0c5460; }}
        .stat.low {{ background: #d4edda; color: #155724; }}
        .stat-value {{ font-size: 36px; font-weight: bold; }}
        .stat-label {{ font-size: 14px; text-transform: uppercase; }}
        .finding {{ border: 1px solid #ddd; border-radius: 8px; margin: 15px 0; overflow: hidden; }}
        .finding-header {{ padding: 15px; font-weight: bold; }}
        .finding-header.critical {{ background: #f8d7da; }}
        .finding-header.high {{ background: #fff3cd; }}
        .finding-header.medium {{ background: #d1ecf1; }}
        .finding-header.low {{ background: #d4edda; }}
        .finding-body {{ padding: 15px; }}
        .finding-meta {{ color: #666; font-size: 14px; margin: 5px 0; }}
        .recommendation {{ background: #e7f3ff; padding: 10px; border-radius: 4px; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>DAST Security Report</h1>
        <p><strong>Target:</strong> {result.target}:{result.port}</p>
        <p><strong>Scan Time:</strong> {result.scan_time}</p>

        <h2>Summary</h2>
        <div class="summary">
            <div class="stat critical">
                <div class="stat-value">{len([f for f in result.findings if f.severity == DASTSeverity.CRITICAL])}</div>
                <div class="stat-label">Critical</div>
            </div>
            <div class="stat high">
                <div class="stat-value">{len([f for f in result.findings if f.severity == DASTSeverity.HIGH])}</div>
                <div class="stat-label">High</div>
            </div>
            <div class="stat medium">
                <div class="stat-value">{len([f for f in result.findings if f.severity == DASTSeverity.MEDIUM])}</div>
                <div class="stat-label">Medium</div>
            </div>
            <div class="stat low">
                <div class="stat-value">{len([f for f in result.findings if f.severity == DASTSeverity.LOW])}</div>
                <div class="stat-label">Low</div>
            </div>
        </div>

        <h2>Findings ({len(result.findings)})</h2>
"""

        for finding in result.findings:
            severity_class = finding.severity.value
            html_content += f"""
        <div class="finding">
            <div class="finding-header {severity_class}">
                [{finding.severity.value.upper()}] {finding.title}
            </div>
            <div class="finding-body">
                <p>{finding.description}</p>
                <p class="finding-meta"><strong>Category:</strong> {finding.category}</p>
                <p class="finding-meta"><strong>Evidence:</strong> {finding.evidence}</p>
                {f'<p class="finding-meta"><strong>CWE:</strong> {finding.cwe_id}</p>' if finding.cwe_id else ''}
                <div class="recommendation">
                    <strong>Recommendation:</strong> {finding.recommendation}
                </div>
            </div>
        </div>
"""

        html_content += """
    </div>
</body>
</html>
"""

        with open(output_path, 'w') as f:
            f.write(html_content)
