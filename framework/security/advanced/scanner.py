"""Analyzer extracted from advanced_security (mechanical split; see advanced/base.py)."""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Pattern, Set, Tuple, Union
from urllib.parse import parse_qs, urlparse

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

logger = logging.getLogger(__name__)


class AdvancedSecurityScanner:
    """
    Enterprise-grade security scanner

    Provides comprehensive security analysis for mobile applications
    """

    def __init__(self):
        self.secrets_scanner = HardcodedSecretsScanner()
        self.cert_analyzer = CertificatePinningAnalyzer()
        self.binary_analyzer = BinarySecurityAnalyzer()
        self.privacy_checker = PrivacyComplianceChecker()
        self.root_analyzer = RootJailbreakAnalyzer()
        self.code_analyzer = SecureCodingAnalyzer()

        self.all_vulnerabilities: List[SecurityVulnerability] = []
        self.scan_start_time: Optional[datetime] = None
        self.scan_end_time: Optional[datetime] = None

    def full_scan(self, project_dir: Path, platform: str = "android") -> Dict[str, Any]:
        """
        Perform comprehensive security scan

        Args:
            project_dir: Path to project directory
            platform: 'android' or 'ios'

        Returns:
            Comprehensive security report
        """
        self.scan_start_time = datetime.now()
        self.all_vulnerabilities = []

        logger.info(f"Starting security scan of {project_dir}")

        # 1. Hardcoded secrets scan
        logger.info("Scanning for hardcoded secrets...")
        self.all_vulnerabilities.extend(self.secrets_scanner.scan_directory(project_dir))

        # 2. Certificate pinning analysis
        logger.info("Analyzing certificate pinning...")
        if platform == "android":
            self.all_vulnerabilities.extend(self.cert_analyzer.analyze_android(project_dir))
        else:
            self.all_vulnerabilities.extend(self.cert_analyzer.analyze_ios(project_dir))

        # 3. Privacy compliance
        logger.info("Checking privacy compliance...")
        self.all_vulnerabilities.extend(self.privacy_checker.check_pii_logging(project_dir))
        self.all_vulnerabilities.extend(self.privacy_checker.check_tracking_sdks(project_dir))

        # 4. Root/Jailbreak detection
        logger.info("Analyzing root/jailbreak detection...")
        self.all_vulnerabilities.extend(self.root_analyzer.analyze(project_dir, platform))

        # 5. Secure coding practices
        logger.info("Analyzing secure coding practices...")
        self.all_vulnerabilities.extend(self.code_analyzer.analyze(project_dir))

        # 6. Binary analysis (if APK provided)
        apk_files = list(project_dir.rglob("*.apk"))
        for apk_file in apk_files:
            logger.info(f"Analyzing APK: {apk_file}")
            self.all_vulnerabilities.extend(self.binary_analyzer.analyze_android_apk(apk_file))

        # 7. Native library analysis
        for so_file in project_dir.rglob("*.so"):
            logger.info(f"Analyzing native library: {so_file}")
            self.all_vulnerabilities.extend(self.binary_analyzer.analyze_native_libraries(so_file))

        self.scan_end_time = datetime.now()

        return self.generate_report()

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive security report"""
        # Calculate risk score
        risk_score = self._calculate_risk_score()

        # Group by category
        by_category = {}
        for vuln in self.all_vulnerabilities:
            cat = vuln.owasp_category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(vuln.to_dict())

        # Group by severity
        by_severity = {level.name: [] for level in RiskLevel}
        for vuln in self.all_vulnerabilities:
            by_severity[vuln.risk_level.name].append(vuln.to_dict())

        return {
            "scan_info": {
                "start_time": self.scan_start_time.isoformat() if self.scan_start_time else None,
                "end_time": self.scan_end_time.isoformat() if self.scan_end_time else None,
                "duration_seconds": (
                    (self.scan_end_time - self.scan_start_time).total_seconds()
                    if self.scan_start_time and self.scan_end_time
                    else 0
                ),
                "total_vulnerabilities": len(self.all_vulnerabilities),
            },
            "risk_assessment": {
                "overall_score": risk_score,
                "rating": self._get_risk_rating(risk_score),
                "critical_count": len([v for v in self.all_vulnerabilities if v.risk_level == RiskLevel.CRITICAL]),
                "high_count": len([v for v in self.all_vulnerabilities if v.risk_level == RiskLevel.HIGH]),
                "medium_count": len([v for v in self.all_vulnerabilities if v.risk_level == RiskLevel.MEDIUM]),
                "low_count": len([v for v in self.all_vulnerabilities if v.risk_level == RiskLevel.LOW]),
            },
            "by_owasp_category": by_category,
            "by_severity": by_severity,
            "all_vulnerabilities": [v.to_dict() for v in self.all_vulnerabilities],
            "recommendations": self._generate_recommendations(),
        }

    def _calculate_risk_score(self) -> float:
        """Calculate overall risk score (0-100)"""
        if not self.all_vulnerabilities:
            return 0.0

        # Weight by severity
        weights = {RiskLevel.CRITICAL: 10, RiskLevel.HIGH: 7, RiskLevel.MEDIUM: 4, RiskLevel.LOW: 2, RiskLevel.INFO: 1}

        total_weight = sum(weights[v.risk_level] for v in self.all_vulnerabilities)
        max_possible = len(self.all_vulnerabilities) * 10

        # Normalize to 0-100 scale (inverted - higher is worse)
        score = (total_weight / max_possible) * 100 if max_possible > 0 else 0

        return round(min(100, score), 1)

    def _get_risk_rating(self, score: float) -> str:
        """Get risk rating from score"""
        if score >= 70:
            return "CRITICAL"
        elif score >= 50:
            return "HIGH"
        elif score >= 30:
            return "MEDIUM"
        elif score >= 10:
            return "LOW"
        else:
            return "MINIMAL"

    def _generate_recommendations(self) -> List[str]:
        """Generate prioritized recommendations"""
        recommendations = []

        critical = [v for v in self.all_vulnerabilities if v.risk_level == RiskLevel.CRITICAL]
        high = [v for v in self.all_vulnerabilities if v.risk_level == RiskLevel.HIGH]

        if critical:
            recommendations.append(
                f"URGENT: Address {len(critical)} critical vulnerabilities immediately. "
                "These pose immediate risk to application security."
            )

        if high:
            recommendations.append(f"HIGH PRIORITY: Fix {len(high)} high-severity issues within the next sprint.")

        # Specific recommendations based on findings
        categories_found = set(v.owasp_category for v in self.all_vulnerabilities)

        if OWASPMobileTop10.M1_IMPROPER_CREDENTIAL_USAGE in categories_found:
            recommendations.append(
                "Implement secure credential storage using Android Keystore / iOS Keychain. "
                "Never hardcode secrets in source code."
            )

        if OWASPMobileTop10.M5_INSECURE_COMMUNICATION in categories_found:
            recommendations.append("Implement certificate pinning and ensure all communications use TLS 1.2+.")

        if OWASPMobileTop10.M6_INADEQUATE_PRIVACY in categories_found:
            recommendations.append(
                "Review data collection practices and implement GDPR/CCPA compliant consent management."
            )

        return recommendations

    def export_sarif(self, output_path: Path) -> None:
        """Export results in SARIF format for CI/CD integration"""
        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Mobile Test Recorder Security Scanner",
                            "version": "1.0.0",
                            "informationUri": "https://github.com/example/mobile-test-recorder",
                            "rules": [],
                        }
                    },
                    "results": [],
                }
            ],
        }

        # Add rules and results
        rules_added = set()
        for vuln in self.all_vulnerabilities:
            rule_id = vuln.id.split("-")[0]
            if rule_id not in rules_added:
                sarif["runs"][0]["tool"]["driver"]["rules"].append(
                    {
                        "id": rule_id,
                        "name": vuln.title,
                        "shortDescription": {"text": vuln.description[:200]},
                        "helpUri": vuln.references[0] if vuln.references else "",
                    }
                )
                rules_added.add(rule_id)

            sarif["runs"][0]["results"].append(
                {
                    "ruleId": vuln.id,
                    "level": "error" if vuln.risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH] else "warning",
                    "message": {"text": vuln.description},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": vuln.location.split(":")[0]},
                                "region": {
                                    "startLine": int(vuln.location.split(":")[1]) if ":" in vuln.location else 1
                                },
                            }
                        }
                    ],
                }
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(sarif, f, indent=2)

    def export_html_report(self, output_path: Path) -> None:
        """Export detailed HTML report"""
        report = self.generate_report()

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Security Scan Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0 0 10px 0; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }}
        .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .card h3 {{ margin-top: 0; color: #333; }}
        .score {{ font-size: 48px; font-weight: bold; }}
        .score.critical {{ color: #dc3545; }}
        .score.high {{ color: #fd7e14; }}
        .score.medium {{ color: #ffc107; }}
        .score.low {{ color: #28a745; }}
        .vulnerability {{ background: white; padding: 20px; border-radius: 10px; margin-bottom: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-left: 5px solid; }}
        .vulnerability.CRITICAL {{ border-color: #dc3545; }}
        .vulnerability.HIGH {{ border-color: #fd7e14; }}
        .vulnerability.MEDIUM {{ border-color: #ffc107; }}
        .vulnerability.LOW {{ border-color: #28a745; }}
        .vulnerability h4 {{ margin-top: 0; }}
        .badge {{ display: inline-block; padding: 3px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; color: white; }}
        .badge.CRITICAL {{ background: #dc3545; }}
        .badge.HIGH {{ background: #fd7e14; }}
        .badge.MEDIUM {{ background: #ffc107; color: #333; }}
        .badge.LOW {{ background: #28a745; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
        .recommendations {{ background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 20px; }}
        .recommendations h3 {{ color: #1565c0; margin-top: 0; }}
        .recommendations ul {{ margin-bottom: 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Security Scan Report</h1>
            <p>Generated: {report['scan_info']['end_time']}</p>
            <p>Duration: {report['scan_info']['duration_seconds']:.2f} seconds</p>
        </div>

        <div class="summary">
            <div class="card">
                <h3>Risk Score</h3>
                <div class="score {report['risk_assessment']['rating'].lower()}">{report['risk_assessment']['overall_score']}</div>
                <p>Rating: {report['risk_assessment']['rating']}</p>
            </div>
            <div class="card">
                <h3>Critical</h3>
                <div class="score critical">{report['risk_assessment']['critical_count']}</div>
            </div>
            <div class="card">
                <h3>High</h3>
                <div class="score high">{report['risk_assessment']['high_count']}</div>
            </div>
            <div class="card">
                <h3>Medium</h3>
                <div class="score medium">{report['risk_assessment']['medium_count']}</div>
            </div>
            <div class="card">
                <h3>Low</h3>
                <div class="score low">{report['risk_assessment']['low_count']}</div>
            </div>
        </div>

        <h2>Vulnerabilities ({report['scan_info']['total_vulnerabilities']} total)</h2>
"""

        # Add vulnerabilities
        for vuln in sorted(self.all_vulnerabilities, key=lambda v: v.risk_level.value, reverse=True):
            html += f"""
        <div class="vulnerability {vuln.risk_level.name}">
            <h4><span class="badge {vuln.risk_level.name}">{vuln.risk_level.name}</span> {vuln.title}</h4>
            <p><strong>Category:</strong> {vuln.owasp_category.value}</p>
            <p><strong>Location:</strong> <code>{vuln.location}</code></p>
            <p>{vuln.description}</p>
            <p><strong>Evidence:</strong> <code>{vuln.evidence[:200]}...</code></p>
            <p><strong>Remediation:</strong> {vuln.remediation}</p>
            <p><strong>CWE:</strong> {', '.join(f'CWE-{cwe}' for cwe in vuln.cwe_ids)}</p>
        </div>
"""

        # Add recommendations
        html += """
        <div class="recommendations">
            <h3>Recommendations</h3>
            <ul>
"""
        for rec in report["recommendations"]:
            html += f"                <li>{rec}</li>\n"

        html += """
            </ul>
        </div>
    </div>
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)
