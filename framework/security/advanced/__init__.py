"""
Advanced security analyzers (split out of the former advanced_security god file).

One module per analyzer; this package re-exports the full surface so existing
`from framework.security.advanced_security import X` imports keep working via the
thin advanced_security.py shim.
"""

from framework.security.advanced.base import (
    OWASPMobileTop10,
    RiskLevel,
    SecurityVulnerability,
    SecretPattern,
)
from framework.security.advanced.secrets import HardcodedSecretsScanner
from framework.security.advanced.pinning import CertificatePinningAnalyzer
from framework.security.advanced.binary import BinarySecurityAnalyzer
from framework.security.advanced.privacy import PrivacyComplianceChecker
from framework.security.advanced.jailbreak import RootJailbreakAnalyzer
from framework.security.advanced.secure_coding import SecureCodingAnalyzer
from framework.security.advanced.scanner import AdvancedSecurityScanner

__all__ = [
    "OWASPMobileTop10",
    "RiskLevel",
    "SecurityVulnerability",
    "SecretPattern",
    "HardcodedSecretsScanner",
    "CertificatePinningAnalyzer",
    "BinarySecurityAnalyzer",
    "PrivacyComplianceChecker",
    "RootJailbreakAnalyzer",
    "SecureCodingAnalyzer",
    "AdvancedSecurityScanner",
]
