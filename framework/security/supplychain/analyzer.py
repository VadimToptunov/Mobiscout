"""Extracted from supply_chain (mechanical split; see supplychain/base.py)."""

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

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


class SupplyChainAnalyzer:
    """
    Comprehensive Supply Chain Analyzer

    Analyzes all dependencies for security vulnerabilities.
    """

    def __init__(self):
        self.python_parser = PythonDependencyParser()
        self.js_parser = JavaScriptDependencyParser()
        self.gradle_parser = GradleDependencyParser()
        self.cocoapods_parser = CocoaPodsDependencyParser()

    def scan_directory(self, directory: Path) -> Tuple[List[Dependency], List[SupplyChainFinding]]:
        """Scan directory for dependencies and vulnerabilities"""
        dependencies = []
        findings = []

        # Python
        for req_file in directory.rglob("requirements*.txt"):
            deps = self.python_parser.parse_requirements(req_file)
            dependencies.extend(deps)
            findings.extend(self._check_python_vulnerabilities(deps))

        for pyproject in directory.rglob("pyproject.toml"):
            deps = self.python_parser.parse_pyproject(pyproject)
            dependencies.extend(deps)
            findings.extend(self._check_python_vulnerabilities(deps))

        # JavaScript
        for package_json in directory.rglob("package.json"):
            if "node_modules" not in str(package_json):
                deps = self.js_parser.parse_package_json(package_json)
                dependencies.extend(deps)
                findings.extend(self._check_js_vulnerabilities(deps))

        # Gradle
        for gradle_file in directory.rglob("build.gradle*"):
            deps = self.gradle_parser.parse_build_gradle(gradle_file)
            dependencies.extend(deps)
            findings.extend(self._check_gradle_vulnerabilities(deps))

        # CocoaPods
        for podfile_lock in directory.rglob("Podfile.lock"):
            deps = self.cocoapods_parser.parse_podfile_lock(podfile_lock)
            dependencies.extend(deps)

        # Check licenses
        findings.extend(self._check_licenses(dependencies))

        return dependencies, findings

    def _check_python_vulnerabilities(self, dependencies: List[Dependency]) -> List[SupplyChainFinding]:
        """Check Python dependencies for vulnerabilities"""
        findings = []

        for dep in dependencies:
            if dep.name in PythonDependencyParser.KNOWN_VULNERABILITIES:
                for vuln_spec, cve, severity, desc in PythonDependencyParser.KNOWN_VULNERABILITIES[dep.name]:
                    if self._version_matches(dep.version, vuln_spec):
                        findings.append(
                            SupplyChainFinding(
                                finding_type="vulnerability",
                                severity=severity,
                                title=f"Vulnerable dependency: {dep.name}",
                                description=desc,
                                dependency=dep,
                                vulnerability=Vulnerability(
                                    cve_id=cve,
                                    severity=severity,
                                    title=desc,
                                    description=desc,
                                    affected_package=dep.name,
                                    affected_versions=vuln_spec,
                                    fixed_version=None,
                                    cvss_score=None,
                                ),
                                recommendation=f"Upgrade {dep.name} to a version that fixes {cve}",
                            )
                        )

        return findings

    def _check_js_vulnerabilities(self, dependencies: List[Dependency]) -> List[SupplyChainFinding]:
        """Check JavaScript dependencies for vulnerabilities"""
        findings = []

        for dep in dependencies:
            if dep.name in JavaScriptDependencyParser.KNOWN_VULNERABILITIES:
                for vuln_spec, cve, severity, desc in JavaScriptDependencyParser.KNOWN_VULNERABILITIES[dep.name]:
                    if self._version_matches(dep.version, vuln_spec):
                        findings.append(
                            SupplyChainFinding(
                                finding_type="vulnerability",
                                severity=severity,
                                title=f"Vulnerable dependency: {dep.name}",
                                description=desc,
                                dependency=dep,
                                vulnerability=Vulnerability(
                                    cve_id=cve,
                                    severity=severity,
                                    title=desc,
                                    description=desc,
                                    affected_package=dep.name,
                                    affected_versions=vuln_spec,
                                    fixed_version=None,
                                    cvss_score=None,
                                ),
                                recommendation=f"Upgrade {dep.name} to a version that fixes {cve}",
                            )
                        )

        return findings

    def _check_gradle_vulnerabilities(self, dependencies: List[Dependency]) -> List[SupplyChainFinding]:
        """Check Gradle/Java dependencies for vulnerabilities"""
        findings = []

        for dep in dependencies:
            if dep.name in GradleDependencyParser.KNOWN_VULNERABILITIES:
                for vuln_spec, cve, severity, desc in GradleDependencyParser.KNOWN_VULNERABILITIES[dep.name]:
                    if self._version_matches(dep.version, vuln_spec):
                        findings.append(
                            SupplyChainFinding(
                                finding_type="vulnerability",
                                severity=severity,
                                title=f"Vulnerable dependency: {dep.name}",
                                description=desc,
                                dependency=dep,
                                vulnerability=Vulnerability(
                                    cve_id=cve,
                                    severity=severity,
                                    title=desc,
                                    description=desc,
                                    affected_package=dep.name,
                                    affected_versions=vuln_spec,
                                    fixed_version=None,
                                    cvss_score=None,
                                ),
                                recommendation=f"Upgrade {dep.name} to a version that fixes {cve}",
                            )
                        )

        return findings

    def _check_licenses(self, dependencies: List[Dependency]) -> List[SupplyChainFinding]:
        """Check license compliance"""
        findings = []

        for dep in dependencies:
            if dep.license_type == LicenseType.COPYLEFT and not dep.dev_dependency:
                findings.append(
                    SupplyChainFinding(
                        finding_type="license",
                        severity=VulnerabilitySeverity.MEDIUM,
                        title=f"Copyleft license: {dep.name}",
                        description=f"Dependency {dep.name} uses copyleft license {dep.license}",
                        dependency=dep,
                        recommendation="Review license requirements for distribution",
                    )
                )

        return findings

    def _version_matches(self, current: str, spec: str) -> bool:
        """Check if a version satisfies a vulnerability spec (e.g. "<= 5.4")."""
        spec = spec.strip()

        # Match two-char operators before one-char ones, otherwise "<= 5.4"
        # is read as "<" + "= 5.4" and the threshold fails to parse (the old
        # bug: <=/>= branches were dead, and the fallback compared versions
        # lexically so "2.0" < "2.10" came out False).
        op = None
        for candidate in ("<=", ">=", "==", "<", ">"):
            if spec.startswith(candidate):
                op = candidate
                threshold_str = spec[len(candidate) :].strip()
                break
        if op is None:
            return current == spec  # no operator -> exact-match spec

        try:
            from packaging import version as pkg_version

            cur = pkg_version.parse(current)
            thr = pkg_version.parse(threshold_str)
        except ImportError:
            # No packaging available: compare numeric tuples, never lexically.
            def _key(v: str):
                return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))

            cur, thr = _key(current), _key(threshold_str)
        except Exception:
            return False  # unparseable version -> conservatively no match

        return {
            "<=": cur <= thr,
            ">=": cur >= thr,
            "==": cur == thr,
            "<": cur < thr,
            ">": cur > thr,
        }[op]

    def generate_sbom(self, dependencies: List[Dependency]) -> Dict[str, Any]:
        """Generate Software Bill of Materials (SBOM)"""
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.4",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "tools": [{"name": "Mobiscout Framework", "version": "1.0.0"}],
            },
            "components": [
                {
                    "type": "library",
                    "name": dep.name,
                    "version": dep.version,
                    "purl": f"pkg:{dep.dep_type.value}/{dep.name}@{dep.version}",
                }
                for dep in dependencies
            ],
        }

    def get_summary(self, findings: List[SupplyChainFinding]) -> Dict[str, Any]:
        """Get analysis summary"""
        by_severity = {}
        by_type = {}

        for finding in findings:
            sev = finding.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            ftype = finding.finding_type
            by_type[ftype] = by_type.get(ftype, 0) + 1

        return {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_type": by_type,
            "critical": by_severity.get("critical", 0),
            "high": by_severity.get("high", 0),
            "medium": by_severity.get("medium", 0),
            "low": by_severity.get("low", 0),
        }

    def export_report(
        self, dependencies: List[Dependency], findings: List[SupplyChainFinding], output_path: Path
    ) -> None:
        """Export supply chain report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "scan_time": datetime.now().isoformat(),
            "summary": self.get_summary(findings),
            "dependencies": [d.to_dict() for d in dependencies],
            "findings": [f.to_dict() for f in findings],
            "sbom": self.generate_sbom(dependencies),
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    def analyze(self, project_path: Path, check_vulnerabilities: bool = True) -> SupplyChainResult:
        """
        Analyze project for supply chain security issues.

        This is the main entry point for CLI compatibility.
        """
        dependencies, findings = self.scan_directory(project_path)

        # Convert to CLI-compatible format
        result = SupplyChainResult()

        # Group dependencies by name and convert
        deps_by_name: Dict[str, DependencyWithVulns] = {}
        for dep in dependencies:
            key = f"{dep.name}@{dep.version}"
            if key not in deps_by_name:
                deps_by_name[key] = DependencyWithVulns(
                    name=dep.name,
                    version=dep.version,
                    ecosystem=dep.dep_type.value,
                )
        result.dependencies = list(deps_by_name.values())

        # Convert findings to vulnerabilities and license issues
        if check_vulnerabilities:
            for finding in findings:
                if finding.finding_type == "vulnerability" and finding.vulnerability:
                    result.vulnerabilities.append(
                        VulnerabilityInfo(
                            package_name=finding.dependency.name,
                            installed_version=finding.dependency.version,
                            cve_id=finding.vulnerability.cve_id,
                            severity=finding.severity.value,
                            fixed_version=finding.vulnerability.fixed_version,
                            description=finding.description,
                        )
                    )
                elif finding.finding_type == "license":
                    result.license_issues.append(
                        LicenseIssue(
                            package_name=finding.dependency.name,
                            license=finding.dependency.license or "Unknown",
                            issue=finding.description,
                        )
                    )

        return result

    def generate_sbom_file(self, result: SupplyChainResult, output_path: Path, format: str = "cyclonedx") -> None:
        """
        Generate SBOM file from analysis result.

        CLI-compatible wrapper around generate_sbom.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert result dependencies back to Dependency objects for SBOM generation
        deps = [
            Dependency(
                name=d.name,
                version=d.version,
                dep_type=(
                    DependencyType(d.ecosystem)
                    if d.ecosystem in [e.value for e in DependencyType]
                    else DependencyType.PYTHON
                ),
            )
            for d in result.dependencies
        ]

        sbom = self.generate_sbom(deps)

        if format == "spdx":
            # Convert to SPDX format
            sbom = {
                "spdxVersion": "SPDX-2.3",
                "dataLicense": "CC0-1.0",
                "SPDXID": "SPDXRef-DOCUMENT",
                "name": "Supply Chain SBOM",
                "documentNamespace": f"https://example.com/sbom/{datetime.now().isoformat()}",
                "packages": [
                    {
                        "SPDXID": f"SPDXRef-Package-{i}",
                        "name": d.name,
                        "versionInfo": d.version,
                        "downloadLocation": "NOASSERTION",
                    }
                    for i, d in enumerate(result.dependencies)
                ],
            }

        with open(output_path, "w") as f:
            json.dump(sbom, f, indent=2)

    def export_html(self, result: SupplyChainResult, output_path: Path) -> None:
        """Export supply chain analysis to HTML report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        critical_count = len([v for v in result.vulnerabilities if v.severity == "critical"])
        high_count = len([v for v in result.vulnerabilities if v.severity == "high"])

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Supply Chain Security Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
        .stat {{ padding: 20px; border-radius: 8px; text-align: center; }}
        .stat.deps {{ background: #d1ecf1; color: #0c5460; }}
        .stat.critical {{ background: #f8d7da; color: #721c24; }}
        .stat.high {{ background: #fff3cd; color: #856404; }}
        .stat.license {{ background: #d4edda; color: #155724; }}
        .stat-value {{ font-size: 36px; font-weight: bold; }}
        .stat-label {{ font-size: 14px; text-transform: uppercase; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #007bff; color: white; }}
        .severity-critical {{ color: #721c24; font-weight: bold; }}
        .severity-high {{ color: #856404; font-weight: bold; }}
        .severity-medium {{ color: #0c5460; }}
        .severity-low {{ color: #155724; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Supply Chain Security Report</h1>
        <p><strong>Scan Time:</strong> {result.scan_time}</p>

        <div class="summary">
            <div class="stat deps">
                <div class="stat-value">{len(result.dependencies)}</div>
                <div class="stat-label">Dependencies</div>
            </div>
            <div class="stat critical">
                <div class="stat-value">{critical_count}</div>
                <div class="stat-label">Critical</div>
            </div>
            <div class="stat high">
                <div class="stat-value">{high_count}</div>
                <div class="stat-label">High</div>
            </div>
            <div class="stat license">
                <div class="stat-value">{len(result.license_issues)}</div>
                <div class="stat-label">License Issues</div>
            </div>
        </div>

        <h2>Vulnerabilities ({len(result.vulnerabilities)})</h2>
        <table>
            <tr>
                <th>Package</th>
                <th>Version</th>
                <th>CVE</th>
                <th>Severity</th>
                <th>Fixed In</th>
            </tr>
"""

        for vuln in result.vulnerabilities:
            severity_class = f"severity-{vuln.severity}"
            html += f"""
            <tr>
                <td>{vuln.package_name}</td>
                <td>{vuln.installed_version}</td>
                <td>{vuln.cve_id or 'N/A'}</td>
                <td class="{severity_class}">{vuln.severity.upper()}</td>
                <td>{vuln.fixed_version or 'Unknown'}</td>
            </tr>
"""

        html += """
        </table>

        <h2>Dependencies by Ecosystem</h2>
        <table>
            <tr>
                <th>Ecosystem</th>
                <th>Count</th>
            </tr>
"""

        # Group by ecosystem
        by_ecosystem: Dict[str, int] = {}
        for dep in result.dependencies:
            by_ecosystem[dep.ecosystem] = by_ecosystem.get(dep.ecosystem, 0) + 1

        for eco, count in sorted(by_ecosystem.items()):
            html += f"""
            <tr>
                <td>{eco}</td>
                <td>{count}</td>
            </tr>
"""

        html += """
        </table>
    </div>
</body>
</html>
"""

        with open(output_path, "w") as f:
            f.write(html)
