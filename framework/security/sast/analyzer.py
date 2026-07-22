"""Analyzer extracted from sast_analyzer (mechanical split; see sast/base.py)."""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from framework.security.sast.base import (
    Severity,
    SASTFinding,
    SASTResult,
)

from framework.security.sast.taint import TaintAnalyzer
from framework.security.sast.control_flow import ControlFlowAnalyzer
from framework.security.sast.crypto import CryptoAnalyzer
from framework.security.sast.insecure_api import InsecureAPIAnalyzer
from framework.security.sast.android_manifest import AndroidManifestAnalyzer
from framework.security.sast.ios_plist import IOSPlistAnalyzer


class SASTAnalyzer:
    """
    Comprehensive SAST Analyzer

    Combines all static analysis techniques.
    """

    def __init__(self):
        self.taint_analyzer = TaintAnalyzer()
        self.control_flow_analyzer = ControlFlowAnalyzer()
        self.crypto_analyzer = CryptoAnalyzer()
        self.api_analyzer = InsecureAPIAnalyzer()
        self.android_analyzer = AndroidManifestAnalyzer()
        self.ios_analyzer = IOSPlistAnalyzer()

    def analyze_file(self, file_path: Path) -> List[SASTFinding]:
        """Analyze a single file"""
        findings = []
        suffix = file_path.suffix.lower()

        # Taint analysis
        taint_flows = self.taint_analyzer.analyze_file(file_path)
        for flow in taint_flows:
            findings.append(
                SASTFinding(
                    vulnerability_type=flow.vulnerability_type,
                    severity=Severity.HIGH,
                    title=f"Tainted data flow to {flow.sink.sink_type}",
                    description=f"User-controlled data flows from {flow.source.name} to {flow.sink.name}",
                    file_path=str(file_path),
                    line_number=flow.sink.line_number,
                    taint_flow=flow,
                    cwe_id="CWE-20",
                )
            )

        # Control flow analysis (Python)
        if suffix == ".py":
            findings.extend(self.control_flow_analyzer.analyze_python(file_path))

        # Cryptographic analysis
        findings.extend(self.crypto_analyzer.analyze(file_path))

        # Insecure API analysis
        findings.extend(self.api_analyzer.analyze(file_path))

        # Android manifest
        if file_path.name == "AndroidManifest.xml":
            findings.extend(self.android_analyzer.analyze(file_path))

        # iOS plist
        if file_path.name == "Info.plist":
            findings.extend(self.ios_analyzer.analyze(file_path))

        return findings

    def analyze_directory(
        self, directory: Path, recursive: bool = True, exclude_patterns: Optional[List[str]] = None
    ) -> List[SASTFinding]:
        """Analyze all files in directory"""
        findings = []
        exclude = exclude_patterns or ["node_modules", "venv", ".git", "__pycache__", "build", "dist"]

        extensions = {".py", ".java", ".kt", ".swift", ".m", ".h", ".js", ".ts", ".xml", ".plist"}

        def should_exclude(path: Path) -> bool:
            return any(ex in str(path) for ex in exclude)

        pattern = "**/*" if recursive else "*"

        for file_path in directory.glob(pattern):
            if file_path.is_file() and not should_exclude(file_path):
                if file_path.suffix.lower() in extensions or file_path.name in ["AndroidManifest.xml", "Info.plist"]:
                    findings.extend(self.analyze_file(file_path))

        return findings

    def get_summary(self, findings: List[SASTFinding]) -> Dict[str, Any]:
        """Get analysis summary"""
        by_severity = {}
        by_type = {}
        by_cwe = {}

        for finding in findings:
            # By severity
            sev = finding.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            # By type
            vtype = finding.vulnerability_type.value
            by_type[vtype] = by_type.get(vtype, 0) + 1

            # By CWE
            if finding.cwe_id:
                by_cwe[finding.cwe_id] = by_cwe.get(finding.cwe_id, 0) + 1

        return {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_type": by_type,
            "by_cwe": by_cwe,
            "critical": by_severity.get("critical", 0),
            "high": by_severity.get("high", 0),
            "medium": by_severity.get("medium", 0),
            "low": by_severity.get("low", 0),
        }

    def export_sarif(self, findings: List[SASTFinding], output_path: Path) -> None:
        """Export findings in SARIF format"""
        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Mobiscout SAST",
                            "version": "1.0.0",
                            "informationUri": "https://mobiscout-framework.dev",
                            "rules": [],
                        }
                    },
                    "results": [],
                }
            ],
        }

        rules = {}
        results = []

        for finding in findings:
            rule_id = finding.vulnerability_type.value

            if rule_id not in rules:
                rules[rule_id] = {
                    "id": rule_id,
                    "name": finding.title,
                    "shortDescription": {"text": finding.title},
                    "fullDescription": {"text": finding.description},
                    "defaultConfiguration": {
                        "level": "error" if finding.severity in [Severity.CRITICAL, Severity.HIGH] else "warning"
                    },
                    "properties": {
                        "security-severity": str(finding.cvss_score or 7.0),
                    },
                }

            results.append(
                {
                    "ruleId": rule_id,
                    "level": "error" if finding.severity in [Severity.CRITICAL, Severity.HIGH] else "warning",
                    "message": {"text": finding.description},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": finding.file_path},
                                "region": {"startLine": finding.line_number, "startColumn": finding.column or 1},
                            }
                        }
                    ],
                }
            )

        sarif["runs"][0]["tool"]["driver"]["rules"] = list(rules.values())
        sarif["runs"][0]["results"] = results

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(sarif, f, indent=2)

    def analyze(
        self,
        source_path: Path,
        language: str = "auto",
        enable_taint: bool = True,
        enable_crypto: bool = True,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None,
    ) -> SASTResult:
        """
        CLI-compatible analyze method that returns SASTResult wrapper.

        Args:
            source_path: Path to file or directory to analyze
            language: Target language (auto, python, java, kotlin, swift, javascript)
            enable_taint: Enable taint analysis
            enable_crypto: Enable cryptographic weakness detection
            recursive: Recursively analyze directories
            exclude_patterns: Patterns to exclude from analysis

        Returns:
            SASTResult with findings and metadata
        """
        findings = []
        files_scanned = 0

        if source_path.is_file():
            findings = self.analyze_file(source_path)
            files_scanned = 1
        elif source_path.is_dir():
            findings = self.analyze_directory(source_path, recursive=recursive, exclude_patterns=exclude_patterns)
            # Count files scanned
            exclude = exclude_patterns or ["node_modules", "venv", ".git", "__pycache__", "build", "dist"]
            extensions = {".py", ".java", ".kt", ".swift", ".m", ".h", ".js", ".ts", ".xml", ".plist"}

            def should_exclude(path: Path) -> bool:
                return any(ex in str(path) for ex in exclude)

            pattern = "**/*" if recursive else "*"
            for file_path in source_path.glob(pattern):
                if file_path.is_file() and not should_exclude(file_path):
                    if file_path.suffix.lower() in extensions or file_path.name in [
                        "AndroidManifest.xml",
                        "Info.plist",
                    ]:
                        files_scanned += 1

        return SASTResult(
            findings=findings,
            source_path=str(source_path),
            language=language,
            files_scanned=files_scanned,
        )

    def export_html(self, result: SASTResult, output_path: Path) -> None:
        """Export SAST results to HTML report"""
        summary = result.get_summary()

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SAST Analysis Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .summary-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
        .summary-card h3 {{ margin: 0 0 10px; color: #666; font-size: 14px; text-transform: uppercase; }}
        .summary-card .value {{ font-size: 36px; font-weight: bold; }}
        .critical {{ color: #dc3545; }}
        .high {{ color: #fd7e14; }}
        .medium {{ color: #ffc107; }}
        .low {{ color: #28a745; }}
        .findings {{ background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .finding {{ padding: 20px; border-bottom: 1px solid #eee; }}
        .finding:last-child {{ border-bottom: none; }}
        .finding-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .finding-title {{ font-weight: bold; font-size: 16px; }}
        .severity-badge {{ padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; text-transform: uppercase; }}
        .severity-critical {{ background: #dc3545; color: white; }}
        .severity-high {{ background: #fd7e14; color: white; }}
        .severity-medium {{ background: #ffc107; color: #333; }}
        .severity-low {{ background: #28a745; color: white; }}
        .severity-info {{ background: #17a2b8; color: white; }}
        .finding-details {{ color: #666; font-size: 14px; }}
        .finding-location {{ font-family: monospace; background: #f8f9fa; padding: 4px 8px; border-radius: 4px; font-size: 12px; }}
        .code-snippet {{ background: #2d2d2d; color: #f8f8f2; padding: 10px; border-radius: 4px; font-family: monospace; overflow-x: auto; margin-top: 10px; }}
        .metadata {{ margin-top: 10px; display: flex; gap: 15px; flex-wrap: wrap; }}
        .metadata span {{ font-size: 12px; color: #666; }}
        .metadata strong {{ color: #333; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>SAST Analysis Report</h1>
        <p><strong>Source:</strong> {result.source_path}</p>
        <p><strong>Scan Time:</strong> {result.scan_time}</p>
        <p><strong>Files Scanned:</strong> {result.files_scanned}</p>

        <div class="summary">
            <div class="summary-card">
                <h3>Total Findings</h3>
                <div class="value">{summary['total_findings']}</div>
            </div>
            <div class="summary-card">
                <h3>Critical</h3>
                <div class="value critical">{summary['critical']}</div>
            </div>
            <div class="summary-card">
                <h3>High</h3>
                <div class="value high">{summary['high']}</div>
            </div>
            <div class="summary-card">
                <h3>Medium</h3>
                <div class="value medium">{summary['medium']}</div>
            </div>
            <div class="summary-card">
                <h3>Low</h3>
                <div class="value low">{summary['low']}</div>
            </div>
        </div>

        <h2>Findings</h2>
        <div class="findings">
"""

        if not result.findings:
            html_content += '            <div class="finding"><p>No vulnerabilities found.</p></div>\n'
        else:
            for finding in result.findings:
                severity_class = f"severity-{finding.severity.value}"
                html_content += f"""            <div class="finding">
                <div class="finding-header">
                    <span class="finding-title">{finding.title}</span>
                    <span class="severity-badge {severity_class}">{finding.severity.value}</span>
                </div>
                <p class="finding-details">{finding.description}</p>
                <p class="finding-location">{finding.file_path}:{finding.line_number}</p>
"""
                if finding.code_snippet:
                    escaped_snippet = finding.code_snippet.replace("<", "&lt;").replace(">", "&gt;")
                    html_content += f'                <pre class="code-snippet">{escaped_snippet}</pre>\n'

                if finding.recommendation:
                    html_content += (
                        f"                <p><strong>Recommendation:</strong> {finding.recommendation}</p>\n"
                    )

                html_content += '                <div class="metadata">\n'
                if finding.cwe_id:
                    html_content += f"                    <span><strong>CWE:</strong> {finding.cwe_id}</span>\n"
                if finding.owasp_category:
                    html_content += (
                        f"                    <span><strong>OWASP:</strong> {finding.owasp_category}</span>\n"
                    )
                html_content += (
                    f"                    <span><strong>Type:</strong> {finding.vulnerability_type.value}</span>\n"
                )
                html_content += "                </div>\n"
                html_content += "            </div>\n"

        html_content += """        </div>
    </div>
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html_content)
