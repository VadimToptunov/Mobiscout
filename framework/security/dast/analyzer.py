"""Analyzer extracted from dast_analyzer (mechanical split; see dast/base.py)."""

import json
import socket
import ssl
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from framework.security.dast.base import (
    DASTSeverity,
    NetworkRequest,
    DASTFinding,
    SSLAnalysisResult,
    DASTResult,
    APITestResult,
)

from framework.security.dast.ssl_tls import SSLTLSAnalyzer
from framework.security.dast.api import APISecurityTester
from framework.security.dast.traffic import NetworkTrafficAnalyzer
from framework.security.dast.session import SessionAnalyzer


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
        self, base_url: str, endpoints: List[Dict[str, Any]], auth_header: Optional[str] = None
    ) -> List[DASTFinding]:
        """Analyze API endpoints"""
        findings = []

        headers = {"Authorization": auth_header} if auth_header else None

        for endpoint in endpoints:
            url = f"{base_url}{endpoint.get('path', '')}"
            method = endpoint.get("method", "GET")
            params = endpoint.get("params", {})

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

        with open(output_path, "w") as f:
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
                        cert_expiry = cert.get("notAfter", "")
        except (socket.error, ssl.SSLError, OSError):
            pass

        return SSLAnalysisResult(
            findings=findings,
            protocol=protocol,
            cipher_suite=cipher_suite,
            cert_expiry=cert_expiry,
        )

    def test_api(
        self, base_url: str, headers: Optional[Dict[str, str]] = None, endpoints: Optional[List[Dict[str, Any]]] = None
    ) -> APITestResult:
        """
        Test API endpoints for security vulnerabilities.

        Args:
            base_url: Base URL of the API
            headers: Optional headers including authorization
            endpoints: Optional list of endpoint definitions
        """
        findings = []

        # If no endpoints provided, test base URL
        if not endpoints:
            endpoints = [{"path": "/", "method": "GET"}]

        for endpoint in endpoints:
            url = f"{base_url.rstrip('/')}{endpoint.get('path', '/')}"
            method = endpoint.get("method", "GET")
            params = endpoint.get("params", {})

            endpoint_findings = self.api_tester.test_endpoint(url, method, headers, params)

            # Add endpoint info to findings
            for finding in endpoint_findings:
                finding.endpoint = endpoint.get("path", "/")
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

        with open(output_path, "w") as f:
            f.write(html_content)
