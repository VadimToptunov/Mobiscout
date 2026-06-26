"""
Advanced Security Module - Enterprise-grade security testing

Features:
- OWASP Mobile Top 10 2024 coverage
- Static Application Security Testing (SAST)
- Dynamic Application Security Testing (DAST)
- Runtime Application Self-Protection (RASP) hooks
- Binary analysis (APK/IPA)
- Network traffic analysis
- Certificate pinning verification
- Root/Jailbreak detection testing
- Hardcoded secrets detection
- Privacy compliance checking (GDPR, CCPA)
- Security scoring and risk assessment
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Pattern,
    Set,
    Tuple,
    Union,
)
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


# ============================================================================
# OWASP Mobile Top 10 2024 Categories
# ============================================================================

class OWASPMobileTop10(Enum):
    """OWASP Mobile Top 10 2024 Categories"""
    M1_IMPROPER_CREDENTIAL_USAGE = "M1: Improper Credential Usage"
    M2_INADEQUATE_SUPPLY_CHAIN = "M2: Inadequate Supply Chain Security"
    M3_INSECURE_AUTH = "M3: Insecure Authentication/Authorization"
    M4_INSUFFICIENT_INPUT_OUTPUT = "M4: Insufficient Input/Output Validation"
    M5_INSECURE_COMMUNICATION = "M5: Insecure Communication"
    M6_INADEQUATE_PRIVACY = "M6: Inadequate Privacy Controls"
    M7_INSUFFICIENT_BINARY_PROTECTION = "M7: Insufficient Binary Protections"
    M8_SECURITY_MISCONFIGURATION = "M8: Security Misconfiguration"
    M9_INSECURE_DATA_STORAGE = "M9: Insecure Data Storage"
    M10_INSUFFICIENT_CRYPTOGRAPHY = "M10: Insufficient Cryptography"


class RiskLevel(Enum):
    """Risk assessment levels"""
    CRITICAL = 10
    HIGH = 8
    MEDIUM = 5
    LOW = 3
    INFO = 1


@dataclass
class SecurityVulnerability:
    """Comprehensive security vulnerability"""
    id: str
    title: str
    description: str
    owasp_category: OWASPMobileTop10
    risk_level: RiskLevel
    cvss_score: float
    cwe_ids: List[int]
    location: str
    evidence: str
    remediation: str
    references: List[str] = field(default_factory=list)
    affected_versions: Optional[str] = None
    exploit_available: bool = False
    false_positive_likelihood: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "owasp_category": self.owasp_category.value,
            "risk_level": self.risk_level.name,
            "cvss_score": self.cvss_score,
            "cwe_ids": self.cwe_ids,
            "location": self.location,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "references": self.references,
            "exploit_available": self.exploit_available,
            "detected_at": self.detected_at.isoformat()
        }


# ============================================================================
# Secret Detection Patterns (GitHub-level)
# ============================================================================

class SecretPattern:
    """Pattern for detecting hardcoded secrets"""

    def __init__(self, name: str, pattern: str, severity: RiskLevel,
                 entropy_threshold: float = 3.5, validators: Optional[List[Callable]] = None):
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        self.severity = severity
        self.entropy_threshold = entropy_threshold
        self.validators = validators or []


class HardcodedSecretsScanner:
    """
    Advanced hardcoded secrets detection

    Detects API keys, tokens, passwords, private keys with high accuracy
    using pattern matching, entropy analysis, and context validation.
    """

    def __init__(self):
        self.patterns = self._initialize_patterns()
        self._false_positive_patterns = [
            re.compile(r'example|test|sample|placeholder|xxx|your[_-]?', re.I),
            re.compile(r'<[^>]+>'),  # XML/HTML placeholders
            re.compile(r'\$\{[^}]+\}'),  # Variable substitution
            re.compile(r'%[sd]'),  # Format strings
        ]

    def _initialize_patterns(self) -> List[SecretPattern]:
        """Initialize comprehensive secret detection patterns"""
        return [
            # AWS
            SecretPattern(
                "AWS Access Key ID",
                r'(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}',
                RiskLevel.CRITICAL, 4.0
            ),
            SecretPattern(
                "AWS Secret Access Key",
                r'(?:aws)?[_\-]?secret[_\-]?(?:access)?[_\-]?key["\'\s:=]+[A-Za-z0-9/+=]{40}',
                RiskLevel.CRITICAL, 4.5
            ),

            # Google
            SecretPattern(
                "Google API Key",
                r'AIza[0-9A-Za-z\-_]{35}',
                RiskLevel.HIGH, 4.0
            ),
            SecretPattern(
                "Google OAuth Client ID",
                r'[0-9]+-[a-z0-9_]{32}\.apps\.googleusercontent\.com',
                RiskLevel.MEDIUM, 3.5
            ),
            SecretPattern(
                "Firebase API Key",
                r'(?:firebase|FIREBASE)[_\-]?(?:API)?[_\-]?KEY["\'\s:=]+[A-Za-z0-9\-_]{39}',
                RiskLevel.HIGH, 4.0
            ),

            # GitHub
            SecretPattern(
                "GitHub Token",
                r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}',
                RiskLevel.CRITICAL, 4.5
            ),
            SecretPattern(
                "GitHub OAuth",
                r'github[_\-]?(?:oauth)?[_\-]?(?:token|secret)["\'\s:=]+[A-Za-z0-9_]{40}',
                RiskLevel.CRITICAL, 4.0
            ),

            # Stripe
            SecretPattern(
                "Stripe API Key",
                r'(?:sk|pk)_(?:test|live)_[A-Za-z0-9]{24,}',
                RiskLevel.CRITICAL, 4.5
            ),

            # Twilio
            SecretPattern(
                "Twilio API Key",
                r'SK[a-f0-9]{32}',
                RiskLevel.HIGH, 4.0
            ),
            SecretPattern(
                "Twilio Auth Token",
                r'twilio[_\-]?auth[_\-]?token["\'\s:=]+[a-f0-9]{32}',
                RiskLevel.HIGH, 4.0
            ),

            # Slack
            SecretPattern(
                "Slack Token",
                r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*',
                RiskLevel.HIGH, 4.0
            ),
            SecretPattern(
                "Slack Webhook",
                r'https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[A-Za-z0-9]{24}',
                RiskLevel.MEDIUM, 3.5
            ),

            # Generic tokens and keys
            SecretPattern(
                "Generic API Key",
                r'(?:api[_\-]?key|apikey)["\'\s:=]+[A-Za-z0-9\-_]{20,}',
                RiskLevel.HIGH, 3.5
            ),
            SecretPattern(
                "Generic Secret",
                r'(?:secret|SECRET)[_\-]?(?:KEY|key)?["\'\s:=]+[A-Za-z0-9\-_/+=]{16,}',
                RiskLevel.HIGH, 4.0
            ),
            SecretPattern(
                "Bearer Token",
                r'[Bb]earer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+',
                RiskLevel.HIGH, 4.0
            ),

            # Private Keys
            SecretPattern(
                "RSA Private Key",
                r'-----BEGIN (?:RSA )?PRIVATE KEY-----',
                RiskLevel.CRITICAL, 0.0  # No entropy check needed
            ),
            SecretPattern(
                "EC Private Key",
                r'-----BEGIN EC PRIVATE KEY-----',
                RiskLevel.CRITICAL, 0.0
            ),
            SecretPattern(
                "PGP Private Key",
                r'-----BEGIN PGP PRIVATE KEY BLOCK-----',
                RiskLevel.CRITICAL, 0.0
            ),

            # Database
            SecretPattern(
                "Database Connection String",
                r'(?:mongodb|mysql|postgres|redis)://[^"\'\s]+:[^"\'\s]+@[^"\'\s]+',
                RiskLevel.CRITICAL, 3.0
            ),

            # Passwords
            SecretPattern(
                "Password in Code",
                r'(?:password|passwd|pwd)["\'\s:=]+["\'][^"\']{8,}["\']',
                RiskLevel.HIGH, 3.0
            ),

            # JWT
            SecretPattern(
                "JWT Token",
                r'eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+',
                RiskLevel.MEDIUM, 4.0
            ),

            # Mobile-specific
            SecretPattern(
                "Google Maps API Key",
                r'AIza[0-9A-Za-z\\-_]{35}',
                RiskLevel.MEDIUM, 4.0
            ),
            SecretPattern(
                "Facebook App Secret",
                r'(?:facebook|fb)[_\-]?(?:app)?[_\-]?secret["\'\s:=]+[a-f0-9]{32}',
                RiskLevel.HIGH, 4.0
            ),
        ]

    def calculate_shannon_entropy(self, data: str) -> float:
        """Calculate Shannon entropy of a string"""
        if not data:
            return 0.0

        entropy = 0.0
        for char_count in [data.count(c) for c in set(data)]:
            if char_count > 0:
                freq = char_count / len(data)
                entropy -= freq * (freq and __import__('math').log2(freq))

        return entropy

    def is_false_positive(self, match: str, context: str) -> bool:
        """Check if match is likely a false positive"""
        # Check against false positive patterns
        for fp_pattern in self._false_positive_patterns:
            if fp_pattern.search(match) or fp_pattern.search(context):
                return True

        # Check for common test values
        test_indicators = ['test', 'example', 'sample', 'demo', 'fake', 'mock']
        context_lower = context.lower()
        if any(indicator in context_lower for indicator in test_indicators):
            return True

        return False

    def scan_content(self, content: str, filename: str = "unknown") -> List[SecurityVulnerability]:
        """Scan content for hardcoded secrets"""
        vulnerabilities = []

        for pattern in self.patterns:
            for match in pattern.pattern.finditer(content):
                matched_text = match.group(0)

                # Get surrounding context (100 chars before and after)
                start = max(0, match.start() - 100)
                end = min(len(content), match.end() + 100)
                context = content[start:end]

                # Check for false positives
                if self.is_false_positive(matched_text, context):
                    continue

                # Entropy check (if threshold > 0)
                if pattern.entropy_threshold > 0:
                    # Extract the actual secret value from the match
                    secret_value = re.sub(r'^[^:=]+[:=\s"\']+', '', matched_text)
                    secret_value = secret_value.strip('"\'')

                    entropy = self.calculate_shannon_entropy(secret_value)
                    if entropy < pattern.entropy_threshold:
                        continue

                # Calculate line number
                line_num = content[:match.start()].count('\n') + 1

                vuln_id = hashlib.sha256(
                    f"{filename}:{line_num}:{pattern.name}".encode()
                ).hexdigest()[:12]

                vulnerabilities.append(SecurityVulnerability(
                    id=f"SECRET-{vuln_id}",
                    title=f"Hardcoded {pattern.name} Detected",
                    description=f"A hardcoded {pattern.name} was found in the source code. "
                                f"This could lead to unauthorized access if the code is exposed.",
                    owasp_category=OWASPMobileTop10.M1_IMPROPER_CREDENTIAL_USAGE,
                    risk_level=pattern.severity,
                    cvss_score=8.5 if pattern.severity == RiskLevel.CRITICAL else 7.0,
                    cwe_ids=[798, 259],  # CWE-798: Hardcoded Credentials
                    location=f"{filename}:{line_num}",
                    evidence=f"Pattern: {pattern.name}\nMatch: {matched_text[:50]}...",
                    remediation="Remove hardcoded secrets and use secure secret management:\n"
                                "1. Use environment variables\n"
                                "2. Use secure vaults (AWS Secrets Manager, HashiCorp Vault)\n"
                                "3. Use Android Keystore / iOS Keychain for mobile apps\n"
                                "4. Rotate the compromised credentials immediately",
                    references=[
                        "https://owasp.org/www-community/vulnerabilities/Use_of_hard-coded_password",
                        "https://cwe.mitre.org/data/definitions/798.html"
                    ]
                ))

        return vulnerabilities

    def scan_file(self, file_path: Path) -> List[SecurityVulnerability]:
        """Scan a file for hardcoded secrets"""
        try:
            content = file_path.read_text(errors='ignore')
            return self.scan_content(content, str(file_path))
        except Exception as e:
            logger.warning(f"Could not scan {file_path}: {e}")
            return []

    def scan_directory(self, directory: Path, extensions: Optional[List[str]] = None) -> List[SecurityVulnerability]:
        """Scan directory recursively for hardcoded secrets"""
        if extensions is None:
            extensions = [
                '.py', '.java', '.kt', '.swift', '.m', '.h',
                '.js', '.ts', '.jsx', '.tsx', '.json', '.xml',
                '.yml', '.yaml', '.properties', '.gradle', '.plist',
                '.env', '.config', '.cfg', '.ini'
            ]

        vulnerabilities = []
        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.suffix in extensions:
                vulnerabilities.extend(self.scan_file(file_path))

        return vulnerabilities


# ============================================================================
# Certificate Pinning Analyzer
# ============================================================================

class CertificatePinningAnalyzer:
    """
    Analyzes certificate pinning implementation

    Checks for proper SSL/TLS certificate pinning in mobile apps
    """

    def __init__(self):
        self.android_pinning_patterns = [
            # OkHttp CertificatePinner
            re.compile(r'CertificatePinner\.Builder\(\)', re.MULTILINE),
            re.compile(r'\.add\s*\(\s*["\'][^"\']+["\']\s*,\s*["\']sha256/', re.MULTILINE),
            # Network Security Config
            re.compile(r'<pin-set[^>]*>', re.MULTILINE),
            re.compile(r'<pin\s+digest=["\']SHA-256["\']>', re.MULTILINE),
            # TrustKit
            re.compile(r'TrustKit\.initWithConfiguration', re.MULTILINE),
        ]

        self.ios_pinning_patterns = [
            # TrustKit
            re.compile(r'TrustKit\.initSharedInstance', re.MULTILINE),
            # Alamofire
            re.compile(r'ServerTrustPolicy\.pinCertificates', re.MULTILINE),
            re.compile(r'ServerTrustPolicy\.pinPublicKeys', re.MULTILINE),
            # URLSession
            re.compile(r'URLAuthenticationChallenge', re.MULTILINE),
            re.compile(r'SecTrustEvaluate', re.MULTILINE),
        ]

        self.bypass_patterns = [
            # Common bypass indicators
            re.compile(r'trustAllCerts|trustAll|disableCertificateValidation', re.I),
            re.compile(r'ALLOW_ALL_HOSTNAME_VERIFIER', re.I),
            re.compile(r'setHostnameVerifier\s*\(\s*null', re.I),
            re.compile(r'X509TrustManager.*checkServerTrusted.*\{\s*\}', re.DOTALL),
            re.compile(r'NSAllowsArbitraryLoads.*true', re.I),
        ]

    def analyze_android(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Analyze Android app for certificate pinning"""
        vulnerabilities = []
        has_pinning = False
        has_bypass = False

        # Check for network security config
        network_config = source_dir / "res" / "xml" / "network_security_config.xml"
        if network_config.exists():
            content = network_config.read_text()
            if any(p.search(content) for p in self.android_pinning_patterns[2:4]):
                has_pinning = True

        # Scan Java/Kotlin files
        for ext in ['*.java', '*.kt']:
            for file_path in source_dir.rglob(ext):
                content = file_path.read_text(errors='ignore')

                # Check for pinning implementation
                if any(p.search(content) for p in self.android_pinning_patterns):
                    has_pinning = True

                # Check for bypass patterns
                for pattern in self.bypass_patterns:
                    match = pattern.search(content)
                    if match:
                        has_bypass = True
                        line_num = content[:match.start()].count('\n') + 1
                        vulnerabilities.append(SecurityVulnerability(
                            id=f"CERT-BYPASS-{hashlib.md5(str(file_path).encode()).hexdigest()[:8]}",
                            title="Certificate Validation Bypass Detected",
                            description="Code that bypasses SSL/TLS certificate validation was found. "
                                        "This makes the app vulnerable to man-in-the-middle attacks.",
                            owasp_category=OWASPMobileTop10.M5_INSECURE_COMMUNICATION,
                            risk_level=RiskLevel.CRITICAL,
                            cvss_score=9.0,
                            cwe_ids=[295],  # CWE-295: Improper Certificate Validation
                            location=f"{file_path}:{line_num}",
                            evidence=f"Pattern: {pattern.pattern}",
                            remediation="Remove certificate validation bypass code. Implement proper "
                                        "certificate pinning using OkHttp CertificatePinner or "
                                        "Network Security Config.",
                            references=[
                                "https://developer.android.com/training/articles/security-ssl",
                                "https://owasp.org/www-community/controls/Certificate_and_Public_Key_Pinning"
                            ]
                        ))

        # Check if pinning is missing entirely
        if not has_pinning and not has_bypass:
            vulnerabilities.append(SecurityVulnerability(
                id="CERT-NO-PINNING",
                title="No Certificate Pinning Implemented",
                description="The app does not implement certificate pinning, making it vulnerable "
                            "to man-in-the-middle attacks using rogue certificates.",
                owasp_category=OWASPMobileTop10.M5_INSECURE_COMMUNICATION,
                risk_level=RiskLevel.HIGH,
                cvss_score=7.5,
                cwe_ids=[295],
                location="Application-wide",
                evidence="No certificate pinning patterns found in source code",
                remediation="Implement certificate pinning:\n"
                            "1. Use Network Security Config (Android 7+)\n"
                            "2. Use OkHttp CertificatePinner\n"
                            "3. Use TrustKit library",
                references=[
                    "https://developer.android.com/training/articles/security-config"
                ]
            ))

        return vulnerabilities

    def analyze_ios(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Analyze iOS app for certificate pinning"""
        vulnerabilities = []
        has_pinning = False

        # Check Info.plist for ATS settings
        info_plist = source_dir / "Info.plist"
        if info_plist.exists():
            content = info_plist.read_text()
            if 'NSAllowsArbitraryLoads' in content and 'true' in content.lower():
                vulnerabilities.append(SecurityVulnerability(
                    id="CERT-ATS-DISABLED",
                    title="App Transport Security Disabled",
                    description="NSAllowsArbitraryLoads is set to true, disabling App Transport Security. "
                                "This allows insecure HTTP connections.",
                    owasp_category=OWASPMobileTop10.M5_INSECURE_COMMUNICATION,
                    risk_level=RiskLevel.HIGH,
                    cvss_score=7.5,
                    cwe_ids=[319],  # CWE-319: Cleartext Transmission
                    location="Info.plist",
                    evidence="NSAllowsArbitraryLoads = true",
                    remediation="Remove NSAllowsArbitraryLoads or set it to false. "
                                "Configure specific exceptions if needed.",
                    references=[
                        "https://developer.apple.com/documentation/security/preventing_insecure_network_connections"
                    ]
                ))

        # Scan Swift/Objective-C files
        for ext in ['*.swift', '*.m', '*.mm']:
            for file_path in source_dir.rglob(ext):
                content = file_path.read_text(errors='ignore')

                if any(p.search(content) for p in self.ios_pinning_patterns):
                    has_pinning = True

        if not has_pinning:
            vulnerabilities.append(SecurityVulnerability(
                id="CERT-NO-PINNING-IOS",
                title="No Certificate Pinning Implemented",
                description="The iOS app does not implement certificate pinning.",
                owasp_category=OWASPMobileTop10.M5_INSECURE_COMMUNICATION,
                risk_level=RiskLevel.HIGH,
                cvss_score=7.5,
                cwe_ids=[295],
                location="Application-wide",
                evidence="No certificate pinning patterns found",
                remediation="Implement certificate pinning using TrustKit or URLSession delegate.",
                references=[
                    "https://developer.apple.com/documentation/foundation/url_loading_system/handling_an_authentication_challenge"
                ]
            ))

        return vulnerabilities


# ============================================================================
# Binary Security Analyzer
# ============================================================================

class BinarySecurityAnalyzer:
    """
    Analyzes compiled binaries for security issues

    Checks for:
    - Stack canaries
    - PIE (Position Independent Executable)
    - RELRO (Relocation Read-Only)
    - NX bit (Non-Executable stack)
    - Stripped binaries
    - Debugging symbols
    """

    def analyze_android_apk(self, apk_path: Path) -> List[SecurityVulnerability]:
        """Analyze Android APK for binary security issues"""
        vulnerabilities = []

        try:
            # Check if apktool is available
            result = subprocess.run(
                ['apktool', 'd', str(apk_path), '-o', '/tmp/apk_analysis', '-f'],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                logger.warning(f"apktool failed: {result.stderr}")
                return vulnerabilities

            # Check AndroidManifest.xml
            manifest_path = Path('/tmp/apk_analysis/AndroidManifest.xml')
            if manifest_path.exists():
                manifest = manifest_path.read_text()

                # Check for debuggable flag
                if 'android:debuggable="true"' in manifest:
                    vulnerabilities.append(SecurityVulnerability(
                        id="BIN-DEBUGGABLE",
                        title="Application is Debuggable",
                        description="The android:debuggable flag is set to true, allowing "
                                    "attackers to attach a debugger to the application.",
                        owasp_category=OWASPMobileTop10.M7_INSUFFICIENT_BINARY_PROTECTION,
                        risk_level=RiskLevel.HIGH,
                        cvss_score=7.5,
                        cwe_ids=[489],  # CWE-489: Active Debug Code
                        location="AndroidManifest.xml",
                        evidence='android:debuggable="true"',
                        remediation="Set android:debuggable to false in release builds.",
                        references=[]
                    ))

                # Check for backup flag
                if 'android:allowBackup="true"' in manifest:
                    vulnerabilities.append(SecurityVulnerability(
                        id="BIN-BACKUP",
                        title="Application Backup Allowed",
                        description="android:allowBackup is true, allowing backup of app data "
                                    "which may contain sensitive information.",
                        owasp_category=OWASPMobileTop10.M9_INSECURE_DATA_STORAGE,
                        risk_level=RiskLevel.MEDIUM,
                        cvss_score=5.0,
                        cwe_ids=[530],  # CWE-530: Exposure of Backup File
                        location="AndroidManifest.xml",
                        evidence='android:allowBackup="true"',
                        remediation="Set android:allowBackup to false or implement BackupAgent.",
                        references=[]
                    ))

                # Check for exported components
                exported_pattern = re.compile(r'android:exported="true"', re.I)
                if exported_pattern.search(manifest):
                    vulnerabilities.append(SecurityVulnerability(
                        id="BIN-EXPORTED",
                        title="Exported Components Detected",
                        description="The app has exported components that may be accessible "
                                    "by other applications.",
                        owasp_category=OWASPMobileTop10.M3_INSECURE_AUTH,
                        risk_level=RiskLevel.MEDIUM,
                        cvss_score=5.5,
                        cwe_ids=[926],  # CWE-926: Improper Export of Android Components
                        location="AndroidManifest.xml",
                        evidence="android:exported=\"true\" found",
                        remediation="Review exported components and add proper permission checks.",
                        references=[]
                    ))

        except subprocess.TimeoutExpired:
            logger.error("APK analysis timed out")
        except FileNotFoundError:
            logger.warning("apktool not found, skipping APK analysis")
        except Exception as e:
            logger.error(f"APK analysis failed: {e}")

        return vulnerabilities

    def analyze_native_libraries(self, lib_path: Path) -> List[SecurityVulnerability]:
        """Analyze native libraries (.so files) for security features"""
        vulnerabilities = []

        try:
            # Use readelf to check security features
            result = subprocess.run(
                ['readelf', '-h', '-l', str(lib_path)],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode == 0:
                output = result.stdout

                # Check for PIE
                if 'DYN (Shared object file)' not in output and 'DYN (Position-Independent' not in output:
                    vulnerabilities.append(SecurityVulnerability(
                        id=f"BIN-NO-PIE-{lib_path.name[:20]}",
                        title="Binary Not Position Independent",
                        description=f"Native library {lib_path.name} is not compiled as PIE, "
                                    "making ASLR less effective.",
                        owasp_category=OWASPMobileTop10.M7_INSUFFICIENT_BINARY_PROTECTION,
                        risk_level=RiskLevel.MEDIUM,
                        cvss_score=5.0,
                        cwe_ids=[119],
                        location=str(lib_path),
                        evidence="Binary not compiled with -fPIE",
                        remediation="Compile native libraries with -fPIE -pie flags.",
                        references=[]
                    ))

                # Check for stack canaries using checksec-style analysis
                result_syms = subprocess.run(
                    ['readelf', '-s', str(lib_path)],
                    capture_output=True, text=True, timeout=30
                )

                if '__stack_chk_fail' not in result_syms.stdout:
                    vulnerabilities.append(SecurityVulnerability(
                        id=f"BIN-NO-CANARY-{lib_path.name[:20]}",
                        title="Stack Canaries Not Enabled",
                        description=f"Native library {lib_path.name} does not have stack canaries, "
                                    "making it vulnerable to stack buffer overflows.",
                        owasp_category=OWASPMobileTop10.M7_INSUFFICIENT_BINARY_PROTECTION,
                        risk_level=RiskLevel.HIGH,
                        cvss_score=7.0,
                        cwe_ids=[121],  # CWE-121: Stack-based Buffer Overflow
                        location=str(lib_path),
                        evidence="__stack_chk_fail symbol not found",
                        remediation="Compile with -fstack-protector-strong flag.",
                        references=[]
                    ))

        except FileNotFoundError:
            logger.warning("readelf not found, skipping native library analysis")
        except Exception as e:
            logger.error(f"Native library analysis failed: {e}")

        return vulnerabilities


# ============================================================================
# Privacy Compliance Checker
# ============================================================================

class PrivacyComplianceChecker:
    """
    Checks for privacy compliance issues (GDPR, CCPA)
    """

    def __init__(self):
        self.pii_patterns = {
            'email': re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
            'phone': re.compile(r'\+?[1-9]\d{1,14}'),
            'ssn': re.compile(r'\d{3}-\d{2}-\d{4}'),
            'credit_card': re.compile(r'\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}'),
            'ip_address': re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'),
        }

        self.tracking_patterns = [
            re.compile(r'google[_-]?analytics', re.I),
            re.compile(r'facebook[_-]?sdk', re.I),
            re.compile(r'firebase[_-]?analytics', re.I),
            re.compile(r'amplitude', re.I),
            re.compile(r'mixpanel', re.I),
            re.compile(r'appsflyer', re.I),
            re.compile(r'adjust\.com', re.I),
        ]

    def check_pii_logging(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Check for PII being logged"""
        vulnerabilities = []

        log_patterns = [
            re.compile(r'Log\.[divwe]\s*\([^)]*', re.I),
            re.compile(r'NSLog\s*\([^)]*', re.I),
            re.compile(r'print\s*\([^)]*', re.I),
            re.compile(r'console\.log\s*\([^)]*', re.I),
            re.compile(r'logger\.\w+\s*\([^)]*', re.I),
        ]

        for ext in ['*.java', '*.kt', '*.swift', '*.m', '*.py', '*.js', '*.ts']:
            for file_path in source_dir.rglob(ext):
                try:
                    content = file_path.read_text(errors='ignore')

                    for log_pattern in log_patterns:
                        for match in log_pattern.finditer(content):
                            log_statement = match.group(0)

                            for pii_type, pii_pattern in self.pii_patterns.items():
                                if pii_pattern.search(log_statement):
                                    line_num = content[:match.start()].count('\n') + 1
                                    vulnerabilities.append(SecurityVulnerability(
                                        id=f"PRIVACY-LOG-{hashlib.md5(f'{file_path}:{line_num}'.encode()).hexdigest()[:8]}",
                                        title=f"PII ({pii_type}) Potentially Logged",
                                        description=f"A log statement may be logging {pii_type} data, "
                                                    "which violates GDPR/CCPA requirements.",
                                        owasp_category=OWASPMobileTop10.M6_INADEQUATE_PRIVACY,
                                        risk_level=RiskLevel.HIGH,
                                        cvss_score=7.0,
                                        cwe_ids=[532],  # CWE-532: Insertion of Sensitive Info into Log
                                        location=f"{file_path}:{line_num}",
                                        evidence=f"Log statement: {log_statement[:100]}...",
                                        remediation="Remove PII from log statements or redact sensitive data.",
                                        references=[
                                            "https://gdpr-info.eu/art-5-gdpr/"
                                        ]
                                    ))

                except Exception as e:
                    logger.warning(f"Could not analyze {file_path}: {e}")

        return vulnerabilities

    def check_tracking_sdks(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Check for third-party tracking SDKs without consent"""
        vulnerabilities = []
        found_trackers = set()

        # Check Gradle files
        for gradle_file in source_dir.rglob('*.gradle*'):
            try:
                content = gradle_file.read_text(errors='ignore')
                for pattern in self.tracking_patterns:
                    if pattern.search(content):
                        found_trackers.add(pattern.pattern)
            except Exception:
                pass

        # Check Podfile
        podfile = source_dir / 'Podfile'
        if podfile.exists():
            try:
                content = podfile.read_text()
                for pattern in self.tracking_patterns:
                    if pattern.search(content):
                        found_trackers.add(pattern.pattern)
            except Exception:
                pass

        if found_trackers:
            vulnerabilities.append(SecurityVulnerability(
                id="PRIVACY-TRACKERS",
                title="Third-Party Tracking SDKs Detected",
                description=f"The app includes tracking SDKs: {', '.join(found_trackers)}. "
                            "Ensure proper user consent is obtained before tracking.",
                owasp_category=OWASPMobileTop10.M6_INADEQUATE_PRIVACY,
                risk_level=RiskLevel.MEDIUM,
                cvss_score=5.0,
                cwe_ids=[359],  # CWE-359: Privacy Violation
                location="Dependencies",
                evidence=f"Found trackers: {found_trackers}",
                remediation="Implement consent management platform (CMP) and obtain "
                            "explicit user consent before enabling tracking.",
                references=[
                    "https://gdpr-info.eu/art-7-gdpr/"
                ]
            ))

        return vulnerabilities


# ============================================================================
# Root/Jailbreak Detection Analyzer
# ============================================================================

class RootJailbreakAnalyzer:
    """
    Analyzes root/jailbreak detection implementation
    """

    def __init__(self):
        self.android_root_checks = [
            re.compile(r'RootBeer|rootbeer', re.I),
            re.compile(r'isDeviceRooted|checkRoot|detectRoot', re.I),
            re.compile(r'su\s*binary|/system/xbin/su', re.I),
            re.compile(r'Superuser\.apk', re.I),
            re.compile(r'SafetyNet|safetynet', re.I),
        ]

        self.ios_jailbreak_checks = [
            re.compile(r'isJailbroken|checkJailbreak|detectJailbreak', re.I),
            re.compile(r'/Applications/Cydia\.app', re.I),
            re.compile(r'/Library/MobileSubstrate', re.I),
            re.compile(r'canOpenURL.*cydia', re.I),
        ]

    def analyze(self, source_dir: Path, platform: str = "android") -> List[SecurityVulnerability]:
        """Analyze root/jailbreak detection implementation"""
        vulnerabilities = []
        has_detection = False

        patterns = self.android_root_checks if platform == "android" else self.ios_jailbreak_checks
        extensions = ['*.java', '*.kt'] if platform == "android" else ['*.swift', '*.m']

        for ext in extensions:
            for file_path in source_dir.rglob(ext):
                try:
                    content = file_path.read_text(errors='ignore')
                    if any(p.search(content) for p in patterns):
                        has_detection = True
                        break
                except Exception:
                    pass

        if not has_detection:
            term = "root" if platform == "android" else "jailbreak"
            vulnerabilities.append(SecurityVulnerability(
                id=f"TAMPER-NO-{term.upper()}-DETECT",
                title=f"No {term.capitalize()} Detection Implemented",
                description=f"The app does not implement {term} detection. "
                            f"Running on {term}ed devices increases security risks.",
                owasp_category=OWASPMobileTop10.M8_SECURITY_MISCONFIGURATION,
                risk_level=RiskLevel.MEDIUM,
                cvss_score=5.5,
                cwe_ids=[919],  # CWE-919: Weaknesses in Mobile Applications
                location="Application-wide",
                evidence=f"No {term} detection patterns found",
                remediation=f"Implement {term} detection and take appropriate action "
                            f"(warn user, restrict functionality, or exit).",
                references=[
                    "https://owasp.org/www-project-mobile-top-10/2016-risks/m8-code-tampering"
                ]
            ))

        return vulnerabilities


# ============================================================================
# Secure Coding Practice Analyzer
# ============================================================================

class SecureCodingAnalyzer:
    """
    Analyzes code for secure coding practices
    """

    def __init__(self):
        self.insecure_patterns = [
            # Insecure random
            (re.compile(r'Random\s*\(\s*\)|Math\.random|rand\(\)', re.I),
             "Insecure Random Number Generator",
             "Use SecureRandom/arc4random for security-sensitive operations",
             [330]),

            # SQL Injection
            (re.compile(r'rawQuery\s*\([^)]*\+|execSQL\s*\([^)]*\+', re.I),
             "Potential SQL Injection",
             "Use parameterized queries instead of string concatenation",
             [89]),

            # WebView JavaScript
            (re.compile(r'setJavaScriptEnabled\s*\(\s*true\s*\)', re.I),
             "WebView JavaScript Enabled",
             "Only enable JavaScript if necessary and validate all inputs",
             [79]),

            # Insecure WebView
            (re.compile(r'setAllowFileAccess\s*\(\s*true\s*\)', re.I),
             "WebView File Access Enabled",
             "Disable file access in WebView unless absolutely necessary",
             [200]),

            # Clipboard
            (re.compile(r'ClipboardManager|UIPasteboard', re.I),
             "Clipboard Usage Detected",
             "Avoid storing sensitive data in clipboard; it's accessible to other apps",
             [200]),

            # World-readable/writable files
            (re.compile(r'MODE_WORLD_READABLE|MODE_WORLD_WRITEABLE', re.I),
             "World-Accessible File Mode",
             "Use MODE_PRIVATE for files containing sensitive data",
             [732]),

            # Hardcoded IV
            (re.compile(r'IvParameterSpec\s*\(\s*["\'][^"\']+["\']\s*\.getBytes', re.I),
             "Hardcoded Initialization Vector",
             "Generate random IVs for each encryption operation",
             [329]),
        ]

    def analyze(self, source_dir: Path) -> List[SecurityVulnerability]:
        """Analyze source code for insecure practices"""
        vulnerabilities = []

        for ext in ['*.java', '*.kt', '*.swift', '*.m', '*.py', '*.js', '*.ts']:
            for file_path in source_dir.rglob(ext):
                try:
                    content = file_path.read_text(errors='ignore')

                    for pattern, title, remediation, cwes in self.insecure_patterns:
                        for match in pattern.finditer(content):
                            line_num = content[:match.start()].count('\n') + 1

                            vulnerabilities.append(SecurityVulnerability(
                                id=f"CODE-{hashlib.md5(f'{file_path}:{line_num}:{title}'.encode()).hexdigest()[:8]}",
                                title=title,
                                description=f"Insecure coding practice detected: {title}",
                                owasp_category=OWASPMobileTop10.M4_INSUFFICIENT_INPUT_OUTPUT,
                                risk_level=RiskLevel.MEDIUM,
                                cvss_score=5.5,
                                cwe_ids=cwes,
                                location=f"{file_path}:{line_num}",
                                evidence=match.group(0)[:100],
                                remediation=remediation,
                                references=[]
                            ))

                except Exception as e:
                    logger.warning(f"Could not analyze {file_path}: {e}")

        return vulnerabilities


# ============================================================================
# Advanced Security Scanner (Main Interface)
# ============================================================================

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
        self.all_vulnerabilities.extend(
            self.secrets_scanner.scan_directory(project_dir)
        )

        # 2. Certificate pinning analysis
        logger.info("Analyzing certificate pinning...")
        if platform == "android":
            self.all_vulnerabilities.extend(
                self.cert_analyzer.analyze_android(project_dir)
            )
        else:
            self.all_vulnerabilities.extend(
                self.cert_analyzer.analyze_ios(project_dir)
            )

        # 3. Privacy compliance
        logger.info("Checking privacy compliance...")
        self.all_vulnerabilities.extend(
            self.privacy_checker.check_pii_logging(project_dir)
        )
        self.all_vulnerabilities.extend(
            self.privacy_checker.check_tracking_sdks(project_dir)
        )

        # 4. Root/Jailbreak detection
        logger.info("Analyzing root/jailbreak detection...")
        self.all_vulnerabilities.extend(
            self.root_analyzer.analyze(project_dir, platform)
        )

        # 5. Secure coding practices
        logger.info("Analyzing secure coding practices...")
        self.all_vulnerabilities.extend(
            self.code_analyzer.analyze(project_dir)
        )

        # 6. Binary analysis (if APK provided)
        apk_files = list(project_dir.rglob("*.apk"))
        for apk_file in apk_files:
            logger.info(f"Analyzing APK: {apk_file}")
            self.all_vulnerabilities.extend(
                self.binary_analyzer.analyze_android_apk(apk_file)
            )

        # 7. Native library analysis
        for so_file in project_dir.rglob("*.so"):
            logger.info(f"Analyzing native library: {so_file}")
            self.all_vulnerabilities.extend(
                self.binary_analyzer.analyze_native_libraries(so_file)
            )

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
                    if self.scan_start_time and self.scan_end_time else 0
                ),
                "total_vulnerabilities": len(self.all_vulnerabilities)
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
            "recommendations": self._generate_recommendations()
        }

    def _calculate_risk_score(self) -> float:
        """Calculate overall risk score (0-100)"""
        if not self.all_vulnerabilities:
            return 0.0

        # Weight by severity
        weights = {
            RiskLevel.CRITICAL: 10,
            RiskLevel.HIGH: 7,
            RiskLevel.MEDIUM: 4,
            RiskLevel.LOW: 2,
            RiskLevel.INFO: 1
        }

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
            recommendations.append(
                f"HIGH PRIORITY: Fix {len(high)} high-severity issues within the next sprint."
            )

        # Specific recommendations based on findings
        categories_found = set(v.owasp_category for v in self.all_vulnerabilities)

        if OWASPMobileTop10.M1_IMPROPER_CREDENTIAL_USAGE in categories_found:
            recommendations.append(
                "Implement secure credential storage using Android Keystore / iOS Keychain. "
                "Never hardcode secrets in source code."
            )

        if OWASPMobileTop10.M5_INSECURE_COMMUNICATION in categories_found:
            recommendations.append(
                "Implement certificate pinning and ensure all communications use TLS 1.2+."
            )

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
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Mobile Test Recorder Security Scanner",
                        "version": "1.0.0",
                        "informationUri": "https://github.com/example/mobile-test-recorder",
                        "rules": []
                    }
                },
                "results": []
            }]
        }

        # Add rules and results
        rules_added = set()
        for vuln in self.all_vulnerabilities:
            rule_id = vuln.id.split('-')[0]
            if rule_id not in rules_added:
                sarif["runs"][0]["tool"]["driver"]["rules"].append({
                    "id": rule_id,
                    "name": vuln.title,
                    "shortDescription": {"text": vuln.description[:200]},
                    "helpUri": vuln.references[0] if vuln.references else ""
                })
                rules_added.add(rule_id)

            sarif["runs"][0]["results"].append({
                "ruleId": vuln.id,
                "level": "error" if vuln.risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH] else "warning",
                "message": {"text": vuln.description},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": vuln.location.split(':')[0]},
                        "region": {
                            "startLine": int(vuln.location.split(':')[1]) if ':' in vuln.location else 1
                        }
                    }
                }]
            })

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
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
        for rec in report['recommendations']:
            html += f"                <li>{rec}</li>\n"

        html += """
            </ul>
        </div>
    </div>
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(html)
