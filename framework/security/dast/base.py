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

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional


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


from framework.security.types import Severity as DASTSeverity  # noqa: E402  (canonical)


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

    def __post_init__(self) -> None:
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
