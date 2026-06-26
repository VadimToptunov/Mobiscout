"""
Security Module

Comprehensive security scanning and vulnerability analysis for mobile applications.

Features:
- OWASP Mobile Top 10 2024 coverage
- Static Application Security Testing (SAST)
- Dynamic Application Security Testing (DAST)
- Hardcoded secrets detection (GitHub-level accuracy)
- Certificate pinning verification
- Binary security analysis
- Privacy compliance checking (GDPR, CCPA)
- Root/Jailbreak detection analysis
- Supply chain security analysis
- Decompilation and reverse engineering
- Runtime protection analysis
- Taint analysis
- Control flow analysis
"""

from framework.security.scanner import (
    SecurityScanner,
    AndroidSecurityScanner,
    IOSSecurityScanner,
    SecurityScanResult,
    SecurityFinding,
    SeverityLevel,
    SecurityCheckCategory,
)

from framework.security.advanced_security import (
    AdvancedSecurityScanner,
    HardcodedSecretsScanner,
    CertificatePinningAnalyzer,
    BinarySecurityAnalyzer,
    PrivacyComplianceChecker,
    RootJailbreakAnalyzer,
    SecureCodingAnalyzer,
    SecurityVulnerability,
    OWASPMobileTop10,
    RiskLevel,
)

from framework.security.sast_analyzer import (
    SASTAnalyzer,
    SASTFinding,
    TaintAnalyzer,
    TaintFlow,
    ControlFlowAnalyzer,
    CryptoAnalyzer,
    InsecureAPIAnalyzer,
    AndroidManifestAnalyzer,
    IOSPlistAnalyzer,
    VulnerabilityType,
    Severity as SASTSeverity,
)

from framework.security.dast_analyzer import (
    DASTAnalyzer,
    DASTFinding,
    SSLTLSAnalyzer,
    APISecurityTester,
    NetworkTrafficAnalyzer,
    SessionAnalyzer,
    NetworkRequest,
    DASTTestType,
    DASTSeverity,
)

from framework.security.decompiler import (
    Decompiler,
    APKDecompiler,
    IPAAnalyzer,
    NativeLibAnalyzer,
    DecompileResult,
    StringFinding,
    ProtectionType,
    BinaryType,
)

from framework.security.supply_chain import (
    SupplyChainAnalyzer,
    Dependency,
    Vulnerability,
    SupplyChainFinding,
    DependencyType,
    VulnerabilitySeverity,
    LicenseType,
)

from framework.security.runtime_protection import (
    RuntimeProtectionAnalyzer,
    AndroidProtectionAnalyzer,
    IOSProtectionAnalyzer,
    ProtectionAnalysis,
    ProtectionIndicator,
    ProtectionCategory,
    ImplementationQuality,
)

__all__ = [
    # Basic scanners
    "SecurityScanner",
    "AndroidSecurityScanner",
    "IOSSecurityScanner",
    "SecurityScanResult",
    "SecurityFinding",
    "SeverityLevel",
    "SecurityCheckCategory",

    # Advanced security (STEP 9)
    "AdvancedSecurityScanner",
    "HardcodedSecretsScanner",
    "CertificatePinningAnalyzer",
    "BinarySecurityAnalyzer",
    "PrivacyComplianceChecker",
    "RootJailbreakAnalyzer",
    "SecureCodingAnalyzer",
    "SecurityVulnerability",
    "OWASPMobileTop10",
    "RiskLevel",

    # SAST
    "SASTAnalyzer",
    "SASTFinding",
    "TaintAnalyzer",
    "TaintFlow",
    "ControlFlowAnalyzer",
    "CryptoAnalyzer",
    "InsecureAPIAnalyzer",
    "AndroidManifestAnalyzer",
    "IOSPlistAnalyzer",
    "VulnerabilityType",
    "SASTSeverity",

    # DAST
    "DASTAnalyzer",
    "DASTFinding",
    "SSLTLSAnalyzer",
    "APISecurityTester",
    "NetworkTrafficAnalyzer",
    "SessionAnalyzer",
    "NetworkRequest",
    "DASTTestType",
    "DASTSeverity",

    # Decompilation
    "Decompiler",
    "APKDecompiler",
    "IPAAnalyzer",
    "NativeLibAnalyzer",
    "DecompileResult",
    "StringFinding",
    "ProtectionType",
    "BinaryType",

    # Supply Chain
    "SupplyChainAnalyzer",
    "Dependency",
    "Vulnerability",
    "SupplyChainFinding",
    "DependencyType",
    "VulnerabilitySeverity",
    "LicenseType",

    # Runtime Protection
    "RuntimeProtectionAnalyzer",
    "AndroidProtectionAnalyzer",
    "IOSProtectionAnalyzer",
    "ProtectionAnalysis",
    "ProtectionIndicator",
    "ProtectionCategory",
    "ImplementationQuality",
]
