"""Supply-chain analysis (split out of the former supply_chain god file)."""

from framework.security.supplychain.base import (
    DependencyType,
    VulnerabilitySeverity,
    LicenseType,
    Dependency,
    Vulnerability,
    SupplyChainFinding,
    DependencyWithVulns,
    VulnerabilityInfo,
    LicenseIssue,
    SupplyChainResult,
)
from framework.security.supplychain.parsers import (
    PythonDependencyParser,
    JavaScriptDependencyParser,
    GradleDependencyParser,
    CocoaPodsDependencyParser,
)
from framework.security.supplychain.analyzer import SupplyChainAnalyzer

__all__ = [
    "DependencyType",
    "VulnerabilitySeverity",
    "LicenseType",
    "Dependency",
    "Vulnerability",
    "SupplyChainFinding",
    "DependencyWithVulns",
    "VulnerabilityInfo",
    "LicenseIssue",
    "SupplyChainResult",
    "PythonDependencyParser",
    "JavaScriptDependencyParser",
    "GradleDependencyParser",
    "CocoaPodsDependencyParser",
    "SupplyChainAnalyzer",
]
