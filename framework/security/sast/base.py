"""
Static Application Security Testing (SAST) Module

Comprehensive static code analysis for mobile applications.

Features:
- Taint analysis for data flow tracking
- Control flow analysis
- Dead code detection
- Insecure API usage detection
- Cryptographic weakness detection
- Data leakage detection
- SQL injection detection
- Path traversal detection
- Deserialization vulnerability detection
- Hardcoded sensitive data detection
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional


class VulnerabilityType(Enum):
    """SAST vulnerability types"""

    # Injection
    SQL_INJECTION = "sql_injection"
    COMMAND_INJECTION = "command_injection"
    XPATH_INJECTION = "xpath_injection"
    LDAP_INJECTION = "ldap_injection"
    LOG_INJECTION = "log_injection"

    # Cryptography
    WEAK_CRYPTO = "weak_cryptography"
    HARDCODED_KEY = "hardcoded_key"
    INSECURE_RANDOM = "insecure_random"
    WEAK_HASH = "weak_hash"

    # Data Exposure
    SENSITIVE_DATA_LOG = "sensitive_data_logging"
    HARDCODED_CREDENTIALS = "hardcoded_credentials"
    INSECURE_STORAGE = "insecure_storage"
    CLEARTEXT_TRANSMISSION = "cleartext_transmission"

    # Code Quality
    NULL_DEREFERENCE = "null_dereference"
    RESOURCE_LEAK = "resource_leak"
    RACE_CONDITION = "race_condition"
    DEAD_CODE = "dead_code"

    # Mobile Specific
    INSECURE_WEBVIEW = "insecure_webview"
    INSECURE_DEEP_LINK = "insecure_deep_link"
    CLIPBOARD_DATA = "clipboard_data_exposure"
    SCREENSHOT_ENABLED = "screenshot_enabled"
    BACKUP_ENABLED = "backup_enabled"
    DEBUGGABLE = "debuggable_app"

    # Deserialization
    UNSAFE_DESERIALIZATION = "unsafe_deserialization"

    # Path Traversal
    PATH_TRAVERSAL = "path_traversal"

    # XSS
    XSS = "cross_site_scripting"


from framework.security.types import Severity  # noqa: E402  (canonical severity)


@dataclass
class TaintSource:
    """Taint analysis source"""

    name: str
    location: str
    line_number: int
    source_type: str  # user_input, file, network, database


@dataclass
class TaintSink:
    """Taint analysis sink"""

    name: str
    location: str
    line_number: int
    sink_type: str  # sql, command, file, log, network


@dataclass
class TaintFlow:
    """Taint flow from source to sink"""

    source: TaintSource
    sink: TaintSink
    path: List[str]  # intermediate nodes
    vulnerability_type: VulnerabilityType


@dataclass
class SASTFinding:
    """SAST vulnerability finding"""

    vulnerability_type: VulnerabilityType
    severity: Severity
    title: str
    description: str
    file_path: str
    line_number: int
    column: int = 0
    code_snippet: str = ""
    recommendation: str = ""
    cwe_id: Optional[str] = None
    owasp_category: Optional[str] = None
    cvss_score: Optional[float] = None
    taint_flow: Optional[TaintFlow] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vulnerability_type": self.vulnerability_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "code_snippet": self.code_snippet,
            "recommendation": self.recommendation,
            "cwe_id": self.cwe_id,
            "owasp_category": self.owasp_category,
            "cvss_score": self.cvss_score,
            "metadata": self.metadata,
        }


@dataclass
class SASTResult:
    """SAST analysis result wrapper for CLI compatibility"""

    findings: List[SASTFinding] = field(default_factory=list)
    source_path: str = ""
    language: str = "auto"
    scan_time: str = field(default_factory=lambda: "")
    files_scanned: int = 0

    def __post_init__(self):
        from datetime import datetime

        if not self.scan_time:
            self.scan_time = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "source_path": self.source_path,
            "language": self.language,
            "scan_time": self.scan_time,
            "files_scanned": self.files_scanned,
            "summary": self.get_summary(),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics"""
        by_severity = {}
        by_type = {}

        for finding in self.findings:
            sev = finding.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            vtype = finding.vulnerability_type.value
            by_type[vtype] = by_type.get(vtype, 0) + 1

        return {
            "total_findings": len(self.findings),
            "by_severity": by_severity,
            "by_type": by_type,
            "critical": by_severity.get("critical", 0),
            "high": by_severity.get("high", 0),
            "medium": by_severity.get("medium", 0),
            "low": by_severity.get("low", 0),
        }
