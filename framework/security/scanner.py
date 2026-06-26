"""
Security Scanning System

Automated security testing for mobile applications following OWASP Mobile Security standards.

Features:
- OWASP Mobile Top 10 checks
- Certificate pinning verification
- Data leakage detection
- Permission audits
- API security checks
- Code obfuscation verification
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class SeverityLevel(Enum):
    """Security issue severity"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SecurityCheckCategory(Enum):
    """Security check categories (OWASP Mobile Top 10)"""

    DATA_STORAGE = "M1: Improper Platform Usage"
    DATA_LEAKAGE = "M2: Insecure Data Storage"
    INSECURE_COMMUNICATION = "M3: Insecure Communication"
    INSECURE_AUTHENTICATION = "M4: Insecure Authentication"
    INSUFFICIENT_CRYPTOGRAPHY = "M5: Insufficient Cryptography"
    INSECURE_AUTHORIZATION = "M6: Insecure Authorization"
    CLIENT_CODE_QUALITY = "M7: Client Code Quality"
    CODE_TAMPERING = "M8: Code Tampering"
    REVERSE_ENGINEERING = "M9: Reverse Engineering"
    EXTRANEOUS_FUNCTIONALITY = "M10: Extraneous Functionality"


@dataclass
class SecurityFinding:
    """Security vulnerability finding"""

    category: SecurityCheckCategory
    severity: SeverityLevel
    title: str
    description: str
    location: str
    recommendation: str
    cve_id: Optional[str] = None
    evidence: List[str] = field(default_factory=list)


@dataclass
class SecurityScanResult:
    """Complete security scan results"""

    app_name: str
    app_version: str
    platform: str  # android or ios
    findings: List[SecurityFinding] = field(default_factory=list)
    scan_time: str = ""

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SeverityLevel.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SeverityLevel.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SeverityLevel.MEDIUM)

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SeverityLevel.LOW)


class AndroidSecurityScanner:
    """
    Android-specific security checks

    Checks:
    - AndroidManifest.xml permissions
    - ProGuard/R8 obfuscation
    - Certificate pinning
    - Backup flags
    - Debuggable flag
    - Hard-coded secrets
    """

    def scan(self, apk_path: Path) -> List[SecurityFinding]:
        """Run Android security scans"""
        findings: List[SecurityFinding] = []

        # Note: This is a simplified version
        # Production would use tools like MobSF, APKTool, etc.

        findings.extend(self._check_manifest(apk_path))
        findings.extend(self._check_hardcoded_secrets(apk_path))
        findings.extend(self._check_obfuscation(apk_path))

        return findings

    def _check_manifest(self, apk_path: Path) -> List[SecurityFinding]:
        """Check AndroidManifest.xml for security issues"""
        findings = []

        # Placeholder: In production, parse actual manifest
        manifest_content = self._extract_manifest(apk_path)

        # Check debuggable flag
        if 'android:debuggable="true"' in manifest_content:
            findings.append(
                SecurityFinding(
                    category=SecurityCheckCategory.CLIENT_CODE_QUALITY,
                    severity=SeverityLevel.HIGH,
                    title="Debuggable Flag Enabled",
                    description="Application is debuggable in production",
                    location="AndroidManifest.xml",
                    recommendation='Set android:debuggable="false" for release builds',
                )
            )

        # Check backup flag
        if 'android:allowBackup="true"' in manifest_content:
            findings.append(
                SecurityFinding(
                    category=SecurityCheckCategory.DATA_STORAGE,
                    severity=SeverityLevel.MEDIUM,
                    title="Backup Allowed",
                    description="Application data can be backed up",
                    location="AndroidManifest.xml",
                    recommendation='Set android:allowBackup="false" if app handles sensitive data',
                )
            )

        # Check dangerous permissions
        dangerous_permissions = [
            "READ_CONTACTS",
            "READ_SMS",
            "ACCESS_FINE_LOCATION",
            "CAMERA",
            "RECORD_AUDIO",
        ]

        for perm in dangerous_permissions:
            if f"android.permission.{perm}" in manifest_content:
                findings.append(
                    SecurityFinding(
                        category=SecurityCheckCategory.INSECURE_AUTHORIZATION,
                        severity=SeverityLevel.LOW,
                        title=f"Dangerous Permission: {perm}",
                        description=f"App requests {perm} permission",
                        location="AndroidManifest.xml",
                        recommendation="Ensure permission is necessary and properly justified to users",
                    )
                )

        return findings

    def _check_hardcoded_secrets(self, apk_path: Path) -> List[SecurityFinding]:
        """Check for hardcoded secrets in code"""
        findings = []

        # Patterns for common secrets
        patterns = {
            "API Key": r"api[_-]?key['\"]?\s*[:=]\s*['\"][a-zA-Z0-9]{20,}['\"]",
            "AWS Key": r"AKIA[0-9A-Z]{16}",
            "Private Key": r"-----BEGIN (RSA|DSA|EC) PRIVATE KEY-----",
            "Password": r"password['\"]?\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        }

        # In production, extract and scan source files
        code_content = self._extract_source_code(apk_path)

        for secret_type, pattern in patterns.items():
            matches = re.findall(pattern, code_content, re.IGNORECASE)
            if matches:
                findings.append(
                    SecurityFinding(
                        category=SecurityCheckCategory.INSUFFICIENT_CRYPTOGRAPHY,
                        severity=SeverityLevel.CRITICAL,
                        title=f"Hardcoded {secret_type}",
                        description=f"Found {len(matches)} hardcoded {secret_type.lower()}(s) in code",
                        location="Source code",
                        recommendation="Move secrets to secure storage (e.g., Android Keystore)",
                        evidence=[str(m)[:50] + "..." for m in matches[:3]],
                    )
                )

        return findings

    def _check_obfuscation(self, apk_path: Path) -> List[SecurityFinding]:
        """Check if code is obfuscated"""
        findings = []

        # Check for ProGuard/R8 signatures
        # In production, analyze actual bytecode

        is_obfuscated = self._is_code_obfuscated(apk_path)

        if not is_obfuscated:
            findings.append(
                SecurityFinding(
                    category=SecurityCheckCategory.REVERSE_ENGINEERING,
                    severity=SeverityLevel.MEDIUM,
                    title="Code Not Obfuscated",
                    description="Application code is not obfuscated, making reverse engineering easier",
                    location="DEX files",
                    recommendation="Enable ProGuard/R8 obfuscation for release builds",
                )
            )

        return findings

    @staticmethod
    def _extract_manifest(apk_path: Path) -> str:
        """Extract AndroidManifest.xml (placeholder)"""
        # In production: use apktool or similar
        return ""

    @staticmethod
    def _extract_source_code(apk_path: Path) -> str:
        """Extract decompiled source code (placeholder)"""
        # In production: use jadx or similar
        return ""

    @staticmethod
    def _is_code_obfuscated(apk_path: Path) -> bool:
        """Check if code is obfuscated (placeholder)"""
        # In production: analyze class names, method names
        return False


class IOSSecurityScanner:
    """
    iOS-specific security checks

    Checks:
    - Info.plist configuration
    - Certificate pinning
    - Keychain usage
    - App Transport Security (ATS)
    - Binary protection
    """

    def scan(self, ipa_path: Path) -> List[SecurityFinding]:
        """Run iOS security scans"""
        findings: List[SecurityFinding] = []

        findings.extend(self._check_info_plist(ipa_path))
        findings.extend(self._check_ats(ipa_path))
        findings.extend(self._check_binary_protection(ipa_path))

        return findings

    def _check_info_plist(self, ipa_path: Path) -> List[SecurityFinding]:
        """Check Info.plist for security issues"""
        findings = []

        plist_content = self._extract_plist(ipa_path)

        # Check for insecure URL schemes
        if "http://" in plist_content:
            findings.append(
                SecurityFinding(
                    category=SecurityCheckCategory.INSECURE_COMMUNICATION,
                    severity=SeverityLevel.MEDIUM,
                    title="Insecure HTTP URLs",
                    description="App uses insecure HTTP URLs",
                    location="Info.plist",
                    recommendation="Use HTTPS for all network communication",
                )
            )

        return findings

    def _check_ats(self, ipa_path: Path) -> List[SecurityFinding]:
        """Check App Transport Security configuration"""
        findings = []

        plist_content = self._extract_plist(ipa_path)

        if "NSAllowsArbitraryLoads" in plist_content:
            findings.append(
                SecurityFinding(
                    category=SecurityCheckCategory.INSECURE_COMMUNICATION,
                    severity=SeverityLevel.HIGH,
                    title="ATS Disabled",
                    description="App Transport Security is disabled",
                    location="Info.plist",
                    recommendation="Enable ATS and use secure HTTPS connections",
                )
            )

        return findings

    def _check_binary_protection(self, ipa_path: Path) -> List[SecurityFinding]:
        """Check binary protections (PIE, Stack Canaries)"""
        findings = []

        # In production: use otool or similar
        has_pie = self._check_pie(ipa_path)

        if not has_pie:
            findings.append(
                SecurityFinding(
                    category=SecurityCheckCategory.CODE_TAMPERING,
                    severity=SeverityLevel.MEDIUM,
                    title="PIE Not Enabled",
                    description="Position Independent Executable (PIE) not enabled",
                    location="Binary",
                    recommendation="Enable PIE in build settings",
                )
            )

        return findings

    @staticmethod
    def _extract_plist(ipa_path: Path) -> str:
        """Extract Info.plist (placeholder)"""
        return ""

    @staticmethod
    def _check_pie(ipa_path: Path) -> bool:
        """Check if PIE is enabled (placeholder)"""
        return False


class SecurityScanner:
    """
    Main security scanner

    Orchestrates platform-specific scanners and generates reports.
    """

    def __init__(self) -> None:
        self.android_scanner = AndroidSecurityScanner()
        self.ios_scanner = IOSSecurityScanner()

    def scan_android(self, apk_path: Path, app_name: str, app_version: str) -> SecurityScanResult:
        """Scan Android APK"""
        from datetime import datetime

        findings = self.android_scanner.scan(apk_path)

        return SecurityScanResult(
            app_name=app_name,
            app_version=app_version,
            platform="android",
            findings=findings,
            scan_time=datetime.now().isoformat(),
        )

    def scan_ios(self, ipa_path: Path, app_name: str, app_version: str) -> SecurityScanResult:
        """Scan iOS IPA"""
        from datetime import datetime

        findings = self.ios_scanner.scan(ipa_path)

        return SecurityScanResult(
            app_name=app_name,
            app_version=app_version,
            platform="ios",
            findings=findings,
            scan_time=datetime.now().isoformat(),
        )

    def generate_report(self, result: SecurityScanResult, output_path: Path, format: str = "json") -> None:
        """Generate security report"""
        if format == "json":
            self._generate_json_report(result, output_path)
        elif format == "html":
            self._generate_html_report(result, output_path)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_json_report(self, result: SecurityScanResult, output_path: Path) -> None:
        """Generate JSON report"""
        data = {
            "app_name": result.app_name,
            "app_version": result.app_version,
            "platform": result.platform,
            "scan_time": result.scan_time,
            "summary": {
                "total_findings": len(result.findings),
                "critical": result.critical_count,
                "high": result.high_count,
                "medium": result.medium_count,
                "low": result.low_count,
            },
            "findings": [
                {
                    "category": f.category.value,
                    "severity": f.severity.value,
                    "title": f.title,
                    "description": f.description,
                    "location": f.location,
                    "recommendation": f.recommendation,
                    "evidence": f.evidence,
                }
                for f in result.findings
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    def _generate_html_report(self, result: SecurityScanResult, output_path: Path) -> None:
        """Generate HTML report"""
        # Placeholder: Use template similar to test reports
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Security Scan Report - {result.app_name}</title>
    <style>
        body {{ font-family: sans-serif; margin: 40px; }}
        h1 {{ color: #c00; }}
        .finding {{ border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .critical {{ border-left: 5px solid #c00; }}
        .high {{ border-left: 5px solid #f80; }}
        .medium {{ border-left: 5px solid #fa0; }}
        .low {{ border-left: 5px solid #0af; }}
    </style>
</head>
<body>
    <h1>Security Scan: {result.app_name} v{result.app_version}</h1>
    <p>Platform: {result.platform} | Scan Time: {result.scan_time}</p>
    <h2>Summary</h2>
    <p>Critical: {result.critical_count} | High: {result.high_count} |
       Medium: {result.medium_count} | Low: {result.low_count}</p>
    <h2>Findings</h2>
    {"".join(self._format_finding_html(f) for f in result.findings)}
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html_content)

    @staticmethod
    def _format_finding_html(finding: SecurityFinding) -> str:
        """Format single finding as HTML"""
        return f"""
<div class="finding {finding.severity.value}">
    <h3>{finding.title}</h3>
    <p><strong>Category:</strong> {finding.category.value}</p>
    <p><strong>Severity:</strong> {finding.severity.value.upper()}</p>
    <p><strong>Location:</strong> {finding.location}</p>
    <p><strong>Description:</strong> {finding.description}</p>
    <p><strong>Recommendation:</strong> {finding.recommendation}</p>
</div>
"""
