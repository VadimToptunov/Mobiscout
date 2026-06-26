"""
Security analyzer for mobile applications

Analyzes apps for common security issues and vulnerabilities.

STEP 7: Paid Modules Enhancement - Security Analyzer Refactoring
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


class SeverityLevel(Enum):
    """Security issue severity"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SecurityIssue:
    """Represents a security issue"""
    severity: SeverityLevel
    title: str
    description: str
    file: Path
    line: int = 0
    recommendation: str = ""
    cwe_id: str = ""  # Common Weakness Enumeration ID


class SecurityAnalyzer:
    """
    Analyzes mobile applications for security vulnerabilities
    """

    def __init__(self, project_root: Path):
        """
        Initialize security analyzer

        Args:
            project_root: Project root directory
        """
        self.project_root = project_root
        self.issues: List[SecurityIssue] = []

    def analyze(self, platform: str = "android") -> List[SecurityIssue]:
        """
        Perform comprehensive security analysis

        Args:
            platform: Target platform ("android" or "ios")

        Returns:
            List of security issues found
        """
        self.issues = []

        if platform == "android":
            self._analyze_android()
        elif platform == "ios":
            self._analyze_ios()

        return sorted(self.issues, key=lambda i: (i.severity.value, i.title))

    def _analyze_android(self) -> None:
        """Android-specific security checks"""
        # Check hardcoded secrets
        self._check_hardcoded_secrets("kotlin")
        self._check_hardcoded_secrets("java")

        # Check insecure network config
        self._check_network_security_config()

        # Check exported components
        self._check_exported_components()

        # Check weak crypto
        self._check_weak_cryptography()

        # Check debug flags
        self._check_debug_flags()

    def _analyze_ios(self) -> None:
        """iOS-specific security checks"""
        # Check hardcoded secrets
        self._check_hardcoded_secrets("swift")

        # Check Info.plist security
        self._check_info_plist()

        # Check keychain usage
        self._check_keychain_usage()

        # Check weak crypto
        self._check_weak_cryptography()

    def _check_hardcoded_secrets(self, language: str) -> None:
        """Check for hardcoded API keys, passwords, etc."""
        patterns = {
            'api_key': r'api[_-]?key\s*=\s*["\']([^"\']+)["\']',
            'password': r'password\s*=\s*["\']([^"\']+)["\']',
            'token': r'token\s*=\s*["\']([^"\']+)["\']',
            'secret': r'secret\s*=\s*["\']([^"\']+)["\']',
        }

        extensions = {
            'kotlin': ['.kt'],
            'java': ['.java'],
            'swift': ['.swift']
        }

        for ext in extensions.get(language, []):
            for file in self.project_root.rglob(f'*{ext}'):
                if not file.is_file():
                    continue

                try:
                    content = file.read_text()
                    lines = content.split('\n')

                    for line_num, line in enumerate(lines, 1):
                        for secret_type, pattern in patterns.items():
                            if re.search(pattern, line, re.IGNORECASE):
                                self.issues.append(SecurityIssue(
                                    severity=SeverityLevel.HIGH,
                                    title=f"Hardcoded {secret_type} detected",
                                    description=f"Found potential hardcoded {secret_type} in source code",
                                    file=file.relative_to(self.project_root),
                                    line=line_num,
                                    recommendation="Use environment variables or secure storage",
                                    cwe_id="CWE-798"
                                ))
                except (OSError, UnicodeDecodeError) as e:
                    # Skip files that can't be read or decoded
                    logger.debug(f"Could not read file {file}: {e}")

    def _check_network_security_config(self) -> None:
        """Check Android network security configuration"""
        config_file = self.project_root / "app" / "src" / "main" / "res" / "xml" / "network_security_config.xml"

        if not config_file.exists():
            self.issues.append(SecurityIssue(
                severity=SeverityLevel.MEDIUM,
                title="Missing network security configuration",
                description="No network_security_config.xml found",
                file=Path("app/src/main/res/xml/"),
                recommendation="Add network security configuration with certificate pinning"
            ))
            return

        try:
            content = config_file.read_text()

            # Check for cleartext traffic
            if 'cleartextTrafficPermitted="true"' in content:
                self.issues.append(SecurityIssue(
                    severity=SeverityLevel.HIGH,
                    title="Cleartext traffic allowed",
                    description="Application allows insecure HTTP connections",
                    file=config_file.relative_to(self.project_root),
                    recommendation="Disable cleartext traffic and use HTTPS only",
                    cwe_id="CWE-319"
                ))
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Could not read network security config: {e}")

    def _check_exported_components(self) -> None:
        """Check for exported Android components"""
        manifest = self.project_root / "app" / "src" / "main" / "AndroidManifest.xml"

        if not manifest.exists():
            return

        try:
            content = manifest.read_text()

            if 'android:exported="true"' in content:
                self.issues.append(SecurityIssue(
                    severity=SeverityLevel.MEDIUM,
                    title="Exported components detected",
                    description="Application has exported components that may be accessed by other apps",
                    file=manifest.relative_to(self.project_root),
                    recommendation="Review exported components and add permissions if needed"
                ))
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Could not read Android manifest: {e}")

    def _check_weak_cryptography(self) -> None:
        """Check for weak cryptographic algorithms"""
        weak_algorithms = ['MD5', 'SHA1', 'DES', 'RC4']

        for file in self.project_root.rglob('*.kt'):
            if not file.is_file():
                continue

            try:
                content = file.read_text()
                lines = content.split('\n')

                for line_num, line in enumerate(lines, 1):
                    for algorithm in weak_algorithms:
                        if re.search(rf'\b{algorithm}\b', line, re.IGNORECASE):
                            self.issues.append(SecurityIssue(
                                severity=SeverityLevel.HIGH,
                                title=f"Weak cryptographic algorithm: {algorithm}",
                                description=f"Usage of deprecated {algorithm} algorithm detected",
                                file=file.relative_to(self.project_root),
                                line=line_num,
                                recommendation=f"Use SHA-256 or better instead of {algorithm}",
                                cwe_id="CWE-327"
                            ))
            except (OSError, UnicodeDecodeError) as e:
                logger.debug(f"Could not read file {file}: {e}")

    def _check_debug_flags(self) -> None:
        """Check for debug flags in production builds"""
        gradle_file = self.project_root / "app" / "build.gradle.kts"

        if not gradle_file.exists():
            gradle_file = self.project_root / "app" / "build.gradle"

        if not gradle_file.exists():
            return

        try:
            content = gradle_file.read_text()

            if 'debuggable true' in content or 'debuggable = true' in content:
                self.issues.append(SecurityIssue(
                    severity=SeverityLevel.CRITICAL,
                    title="Debuggable flag enabled",
                    description="Application is debuggable in production build",
                    file=gradle_file.relative_to(self.project_root),
                    recommendation="Disable debuggable flag for release builds"
                ))
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Could not read Gradle file: {e}")

    def _check_info_plist(self) -> None:
        """Check iOS Info.plist security settings"""
        info_plist = self.project_root / "Info.plist"

        if not info_plist.exists():
            return

        try:
            content = info_plist.read_text()

            # Check for NSAppTransportSecurity
            if 'NSAllowsArbitraryLoads' in content:
                self.issues.append(SecurityIssue(
                    severity=SeverityLevel.HIGH,
                    title="App Transport Security disabled",
                    description="NSAllowsArbitraryLoads allows insecure connections",
                    file=info_plist.relative_to(self.project_root),
                    recommendation="Enable ATS and use HTTPS only"
                ))
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Could not read Info.plist: {e}")

    def _check_keychain_usage(self) -> None:
        """Check iOS Keychain usage"""
        for file in self.project_root.rglob('*.swift'):
            if not file.is_file():
                continue

            try:
                content = file.read_text()

                # Check for insecure keychain access
                if 'kSecAttrAccessibleAlways' in content:
                    self.issues.append(SecurityIssue(
                        severity=SeverityLevel.MEDIUM,
                        title="Insecure keychain accessibility",
                        description="Keychain item accessible even when device is locked",
                        file=file.relative_to(self.project_root),
                        recommendation="Use kSecAttrAccessibleWhenUnlocked or better"
                    ))
            except (OSError, UnicodeDecodeError) as e:
                logger.debug(f"Could not read file {file}: {e}")

    def generate_report(self) -> str:
        """Generate security analysis report"""
        if not self.issues:
            return "No security issues found."

        report = "SECURITY ANALYSIS REPORT\n"
        report += "=" * 80 + "\n\n"

        # Group by severity
        by_severity: Dict[str, List[SecurityIssue]] = {}
        for issue in self.issues:
            severity = issue.severity.value
            if severity not in by_severity:
                by_severity[severity] = []
            by_severity[severity].append(issue)

        for severity in ['critical', 'high', 'medium', 'low', 'info']:
            if severity in by_severity:
                issues = by_severity[severity]
                report += f"\n{severity.upper()} ({len(issues)} issues):\n"
                report += "-" * 80 + "\n"

                for issue in issues:
                    report += f"\n{issue.title}\n"
                    report += f"  File: {issue.file}"
                    if issue.line:
                        report += f":{issue.line}"
                    report += "\n"
                    report += f"  {issue.description}\n"
                    if issue.recommendation:
                        report += f"  Recommendation: {issue.recommendation}\n"
                    if issue.cwe_id:
                        report += f"  CWE: {issue.cwe_id}\n"

        report += "\n" + "=" * 80 + "\n"
        report += f"Total issues: {len(self.issues)}\n"

        return report
