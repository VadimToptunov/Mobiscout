"""
Supply Chain Security Analyzer

Analyzes dependencies and third-party components for security vulnerabilities.

Features:
- Dependency vulnerability scanning
- License compliance checking
- Outdated dependency detection
- Malicious package detection
- SBOM (Software Bill of Materials) generation
- CVE database lookup
"""

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple


class DependencyType(Enum):
    """Dependency types"""

    PYTHON = "python"
    JAVA = "java"
    KOTLIN = "kotlin"
    SWIFT = "swift"
    JAVASCRIPT = "javascript"
    COCOAPODS = "cocoapods"
    GRADLE = "gradle"


class VulnerabilitySeverity(Enum):
    """Vulnerability severity"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class LicenseType(Enum):
    """License compatibility"""

    PERMISSIVE = "permissive"  # MIT, Apache, BSD
    COPYLEFT = "copyleft"  # GPL, LGPL
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


@dataclass
class Dependency:
    """A software dependency"""

    name: str
    version: str
    dep_type: DependencyType
    direct: bool = True
    dev_dependency: bool = False
    license: Optional[str] = None
    license_type: LicenseType = LicenseType.UNKNOWN
    repository_url: Optional[str] = None
    checksum: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "type": self.dep_type.value,
            "direct": self.direct,
            "dev_dependency": self.dev_dependency,
            "license": self.license,
            "license_type": self.license_type.value,
            "repository_url": self.repository_url,
            "checksum": self.checksum,
        }


@dataclass
class Vulnerability:
    """A known vulnerability"""

    cve_id: str
    severity: VulnerabilitySeverity
    title: str
    description: str
    affected_package: str
    affected_versions: str
    fixed_version: Optional[str]
    cvss_score: Optional[float]
    references: List[str] = field(default_factory=list)
    published_date: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cve_id": self.cve_id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "affected_package": self.affected_package,
            "affected_versions": self.affected_versions,
            "fixed_version": self.fixed_version,
            "cvss_score": self.cvss_score,
            "references": self.references,
            "published_date": self.published_date.isoformat() if self.published_date else None,
        }


@dataclass
class SupplyChainFinding:
    """Supply chain security finding"""

    finding_type: str  # vulnerability, license, outdated, malicious
    severity: VulnerabilitySeverity
    title: str
    description: str
    dependency: Dependency
    vulnerability: Optional[Vulnerability] = None
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_type": self.finding_type,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "dependency": self.dependency.to_dict(),
            "vulnerability": self.vulnerability.to_dict() if self.vulnerability else None,
            "recommendation": self.recommendation,
        }


@dataclass
class DependencyWithVulns:
    """Dependency with its vulnerabilities - for CLI compatibility"""

    name: str
    version: str
    ecosystem: str
    vulnerabilities: List[Vulnerability] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "ecosystem": self.ecosystem,
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
        }


@dataclass
class VulnerabilityInfo:
    """Simplified vulnerability info for CLI - matches CLI expectations"""

    package_name: str
    installed_version: str
    cve_id: Optional[str]
    severity: str  # string for CLI compatibility
    fixed_version: Optional[str]
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_name": self.package_name,
            "installed_version": self.installed_version,
            "cve_id": self.cve_id,
            "severity": self.severity,
            "fixed_version": self.fixed_version,
            "description": self.description,
        }


@dataclass
class LicenseIssue:
    """License compliance issue - for CLI compatibility"""

    package_name: str
    license: str
    issue: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_name": self.package_name,
            "license": self.license,
            "issue": self.issue,
        }


@dataclass
class SupplyChainResult:
    """Complete supply chain analysis result - for CLI compatibility"""

    dependencies: List[DependencyWithVulns] = field(default_factory=list)
    vulnerabilities: List[VulnerabilityInfo] = field(default_factory=list)
    license_issues: List[LicenseIssue] = field(default_factory=list)
    scan_time: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scan_time": self.scan_time,
            "total_dependencies": len(self.dependencies),
            "total_vulnerabilities": len(self.vulnerabilities),
            "dependencies": [d.to_dict() for d in self.dependencies],
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
            "license_issues": [l.to_dict() for l in self.license_issues],
        }
