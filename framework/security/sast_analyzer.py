"""
Static Application Security Testing (SAST) Module

Comprehensive static code analysis for mobile applications.

Features:
- Taint analysis for data flow tracking
- Control flow analysis
- Dead code detection
- Insecure API usage detection
- Cryptographic weakness detection
- Data leakage detection
- SQL injection detection
- Path traversal detection
- Deserialization vulnerability detection
- Hardcoded sensitive data detection
"""

import ast
import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET


class VulnerabilityType(Enum):
    """SAST vulnerability types"""

    # Injection
    SQL_INJECTION = "sql_injection"
    COMMAND_INJECTION = "command_injection"
    XPATH_INJECTION = "xpath_injection"
    LDAP_INJECTION = "ldap_injection"
    LOG_INJECTION = "log_injection"

    # Cryptography
    WEAK_CRYPTO = "weak_cryptography"
    HARDCODED_KEY = "hardcoded_key"
    INSECURE_RANDOM = "insecure_random"
    WEAK_HASH = "weak_hash"

    # Data Exposure
    SENSITIVE_DATA_LOG = "sensitive_data_logging"
    HARDCODED_CREDENTIALS = "hardcoded_credentials"
    INSECURE_STORAGE = "insecure_storage"
    CLEARTEXT_TRANSMISSION = "cleartext_transmission"

    # Code Quality
    NULL_DEREFERENCE = "null_dereference"
    RESOURCE_LEAK = "resource_leak"
    RACE_CONDITION = "race_condition"
    DEAD_CODE = "dead_code"

    # Mobile Specific
    INSECURE_WEBVIEW = "insecure_webview"
    INSECURE_DEEP_LINK = "insecure_deep_link"
    CLIPBOARD_DATA = "clipboard_data_exposure"
    SCREENSHOT_ENABLED = "screenshot_enabled"
    BACKUP_ENABLED = "backup_enabled"
    DEBUGGABLE = "debuggable_app"

    # Deserialization
    UNSAFE_DESERIALIZATION = "unsafe_deserialization"

    # Path Traversal
    PATH_TRAVERSAL = "path_traversal"

    # XSS
    XSS = "cross_site_scripting"


from framework.security.types import Severity  # noqa: E402  (canonical severity)


@dataclass
class TaintSource:
    """Taint analysis source"""

    name: str
    location: str
    line_number: int
    source_type: str  # user_input, file, network, database


@dataclass
class TaintSink:
    """Taint analysis sink"""

    name: str
    location: str
    line_number: int
    sink_type: str  # sql, command, file, log, network


@dataclass
class TaintFlow:
    """Taint flow from source to sink"""

    source: TaintSource
    sink: TaintSink
    path: List[str]  # intermediate nodes
    vulnerability_type: VulnerabilityType


@dataclass
class SASTFinding:
    """SAST vulnerability finding"""

    vulnerability_type: VulnerabilityType
    severity: Severity
    title: str
    description: str
    file_path: str
    line_number: int
    column: int = 0
    code_snippet: str = ""
    recommendation: str = ""
    cwe_id: Optional[str] = None
    owasp_category: Optional[str] = None
    cvss_score: Optional[float] = None
    taint_flow: Optional[TaintFlow] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vulnerability_type": self.vulnerability_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "code_snippet": self.code_snippet,
            "recommendation": self.recommendation,
            "cwe_id": self.cwe_id,
            "owasp_category": self.owasp_category,
            "cvss_score": self.cvss_score,
            "metadata": self.metadata,
        }


@dataclass
class SASTResult:
    """SAST analysis result wrapper for CLI compatibility"""

    findings: List[SASTFinding] = field(default_factory=list)
    source_path: str = ""
    language: str = "auto"
    scan_time: str = field(default_factory=lambda: "")
    files_scanned: int = 0

    def __post_init__(self):
        from datetime import datetime

        if not self.scan_time:
            self.scan_time = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "source_path": self.source_path,
            "language": self.language,
            "scan_time": self.scan_time,
            "files_scanned": self.files_scanned,
            "summary": self.get_summary(),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics"""
        by_severity = {}
        by_type = {}

        for finding in self.findings:
            sev = finding.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            vtype = finding.vulnerability_type.value
            by_type[vtype] = by_type.get(vtype, 0) + 1

        return {
            "total_findings": len(self.findings),
            "by_severity": by_severity,
            "by_type": by_type,
            "critical": by_severity.get("critical", 0),
            "high": by_severity.get("high", 0),
            "medium": by_severity.get("medium", 0),
            "low": by_severity.get("low", 0),
        }


class TaintAnalyzer:
    """
    Taint Analysis Engine

    Tracks data flow from untrusted sources to security-sensitive sinks.
    """

    def __init__(self):
        # Define taint sources (user-controllable inputs)
        self.sources = {
            # Python
            "input": "user_input",
            "request.args": "user_input",
            "request.form": "user_input",
            "request.data": "user_input",
            "request.json": "user_input",
            "request.cookies": "user_input",
            "request.headers": "user_input",
            "sys.argv": "user_input",
            "os.environ": "environment",
            "open(": "file",
            "read(": "file",
            "recv(": "network",
            "recvfrom(": "network",
            "urlopen(": "network",
            "requests.get": "network",
            "requests.post": "network",
            # Android/Kotlin
            "getIntent()": "user_input",
            "getExtras()": "user_input",
            "getStringExtra": "user_input",
            "getQueryParameter": "user_input",
            "getText()": "user_input",
            "getSharedPreferences": "storage",
            # iOS/Swift
            "UserDefaults": "storage",
            "UIPasteboard": "user_input",
            "URLComponents": "user_input",
        }

        # Define taint sinks (security-sensitive operations)
        self.sinks = {
            # SQL
            "execute(": VulnerabilityType.SQL_INJECTION,
            "executemany(": VulnerabilityType.SQL_INJECTION,
            "raw(": VulnerabilityType.SQL_INJECTION,
            "rawQuery(": VulnerabilityType.SQL_INJECTION,
            "execSQL(": VulnerabilityType.SQL_INJECTION,
            # Command
            "os.system(": VulnerabilityType.COMMAND_INJECTION,
            "subprocess.call(": VulnerabilityType.COMMAND_INJECTION,
            "subprocess.run(": VulnerabilityType.COMMAND_INJECTION,
            "subprocess.Popen(": VulnerabilityType.COMMAND_INJECTION,
            "eval(": VulnerabilityType.COMMAND_INJECTION,
            "exec(": VulnerabilityType.COMMAND_INJECTION,
            "Runtime.getRuntime().exec(": VulnerabilityType.COMMAND_INJECTION,
            # File
            "open(": VulnerabilityType.PATH_TRAVERSAL,
            "FileInputStream(": VulnerabilityType.PATH_TRAVERSAL,
            "FileOutputStream(": VulnerabilityType.PATH_TRAVERSAL,
            # XSS
            "innerHTML": VulnerabilityType.XSS,
            "document.write(": VulnerabilityType.XSS,
            "loadUrl(": VulnerabilityType.XSS,
            "evaluateJavascript(": VulnerabilityType.XSS,
            # Logging
            "print(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "Log.d(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "Log.i(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "Log.e(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "NSLog(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "logger.": VulnerabilityType.SENSITIVE_DATA_LOG,
            # Deserialization
            "pickle.load(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "pickle.loads(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "yaml.load(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "ObjectInputStream(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "readObject(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "NSKeyedUnarchiver": VulnerabilityType.UNSAFE_DESERIALIZATION,
        }

        self.tainted_vars: Dict[str, TaintSource] = {}

    def analyze_file(self, file_path: Path) -> List[TaintFlow]:
        """Analyze file for taint flows"""
        flows = []

        try:
            content = file_path.read_text()
            lines = content.splitlines()

            # Track tainted variables
            for i, line in enumerate(lines, 1):
                # Check for sources
                for source_pattern, source_type in self.sources.items():
                    if source_pattern in line:
                        # Extract variable name
                        var_match = re.search(r"(\w+)\s*=", line)
                        if var_match:
                            var_name = var_match.group(1)
                            self.tainted_vars[var_name] = TaintSource(
                                name=var_name,
                                location=str(file_path),
                                line_number=i,
                                source_type=source_type,
                            )

                # Check for sinks using tainted data
                for sink_pattern, vuln_type in self.sinks.items():
                    if sink_pattern in line:
                        # Check if any tainted variable is used
                        for var_name, source in self.tainted_vars.items():
                            if var_name in line:
                                sink = TaintSink(
                                    name=sink_pattern,
                                    location=str(file_path),
                                    line_number=i,
                                    sink_type=vuln_type.value,
                                )
                                flows.append(
                                    TaintFlow(
                                        source=source,
                                        sink=sink,
                                        path=[var_name],
                                        vulnerability_type=vuln_type,
                                    )
                                )

        except (OSError, UnicodeDecodeError):
            pass

        return flows


class ControlFlowAnalyzer:
    """
    Control Flow Analysis

    Analyzes control flow for security issues.
    """

    def analyze_python(self, file_path: Path) -> List[SASTFinding]:
        """Analyze Python file control flow"""
        findings = []

        try:
            content = file_path.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                # Check for unreachable code after return/raise
                if isinstance(node, ast.FunctionDef):
                    findings.extend(self._check_unreachable_code(node, file_path))

                # Check for exception handling issues
                if isinstance(node, ast.Try):
                    findings.extend(self._check_exception_handling(node, file_path))

        except (SyntaxError, OSError, UnicodeDecodeError):
            pass

        return findings

    def _check_unreachable_code(self, func: ast.FunctionDef, file_path: Path) -> List[SASTFinding]:
        """Check for unreachable code"""
        findings = []

        for i, stmt in enumerate(func.body):
            if isinstance(stmt, (ast.Return, ast.Raise)):
                # Check if there's code after return/raise
                if i < len(func.body) - 1:
                    next_stmt = func.body[i + 1]
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.DEAD_CODE,
                            severity=Severity.INFO,
                            title="Unreachable code detected",
                            description=f"Code after return/raise statement in function '{func.name}' is unreachable",
                            file_path=str(file_path),
                            line_number=next_stmt.lineno,
                            recommendation="Remove unreachable code or fix control flow logic",
                            cwe_id="CWE-561",
                        )
                    )

        return findings

    def _check_exception_handling(self, try_node: ast.Try, file_path: Path) -> List[SASTFinding]:
        """Check exception handling issues"""
        findings = []

        for handler in try_node.handlers:
            # Bare except clause
            if handler.type is None:
                findings.append(
                    SASTFinding(
                        vulnerability_type=VulnerabilityType.DEAD_CODE,
                        severity=Severity.MEDIUM,
                        title="Bare except clause",
                        description="Catching all exceptions can hide bugs and make debugging difficult",
                        file_path=str(file_path),
                        line_number=handler.lineno,
                        recommendation="Catch specific exceptions instead of using bare except",
                        cwe_id="CWE-396",
                    )
                )

            # Empty except block
            if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                findings.append(
                    SASTFinding(
                        vulnerability_type=VulnerabilityType.DEAD_CODE,
                        severity=Severity.MEDIUM,
                        title="Empty exception handler",
                        description="Empty exception handler silently swallows errors",
                        file_path=str(file_path),
                        line_number=handler.lineno,
                        recommendation="Handle the exception or log it, don't silently ignore",
                        cwe_id="CWE-390",
                    )
                )

        return findings


class CryptoAnalyzer:
    """
    Cryptographic Weakness Analyzer

    Detects insecure cryptographic implementations.
    """

    # Weak algorithms
    WEAK_ALGORITHMS = {
        "MD5": ("CWE-327", "MD5 is cryptographically broken"),
        "SHA1": ("CWE-327", "SHA1 is considered weak for security purposes"),
        "DES": ("CWE-327", "DES has insufficient key length"),
        "3DES": ("CWE-327", "Triple DES is deprecated"),
        "RC4": ("CWE-327", "RC4 has multiple vulnerabilities"),
        "RC2": ("CWE-327", "RC2 is considered weak"),
        "Blowfish": ("CWE-327", "Blowfish with small key sizes is weak"),
        "ECB": ("CWE-327", "ECB mode doesn't provide semantic security"),
    }

    # Insecure random
    INSECURE_RANDOM = [
        "random.random",
        "random.randint",
        "random.choice",
        "Math.random",
        "java.util.Random",
        "arc4random",  # iOS - not for crypto
    ]

    # Hardcoded key patterns
    KEY_PATTERNS = [
        r'["\']?(?:aes|des|rsa|hmac)?[_-]?(?:key|secret|password)["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
        r'(?:private|secret|encryption)[_-]?key\s*=\s*["\'][^"\']+["\']',
        r'iv\s*=\s*["\'][0-9a-fA-F]{16,}["\']',
        r'nonce\s*=\s*["\'][0-9a-fA-F]+["\']',
    ]

    def analyze(self, file_path: Path) -> List[SASTFinding]:
        """Analyze file for cryptographic weaknesses"""
        findings = []

        try:
            content = file_path.read_text()
            lines = content.splitlines()

            for i, line in enumerate(lines, 1):
                lower_line = line.lower()

                # Check weak algorithms
                for algo, (cwe, desc) in self.WEAK_ALGORITHMS.items():
                    if algo.lower() in lower_line:
                        # Skip if it's a comment
                        stripped = line.strip()
                        if stripped.startswith(("#", "//", "/*", "*")):
                            continue

                        findings.append(
                            SASTFinding(
                                vulnerability_type=VulnerabilityType.WEAK_CRYPTO,
                                severity=Severity.HIGH,
                                title=f"Weak cryptographic algorithm: {algo}",
                                description=desc,
                                file_path=str(file_path),
                                line_number=i,
                                code_snippet=line.strip(),
                                recommendation=f"Replace {algo} with a stronger algorithm (AES-256, SHA-256, etc.)",
                                cwe_id=cwe,
                                owasp_category="M5: Insufficient Cryptography",
                            )
                        )

                # Check insecure random
                for pattern in self.INSECURE_RANDOM:
                    if pattern.lower() in lower_line:
                        findings.append(
                            SASTFinding(
                                vulnerability_type=VulnerabilityType.INSECURE_RANDOM,
                                severity=Severity.MEDIUM,
                                title="Insecure random number generator",
                                description=f"'{pattern}' is not cryptographically secure",
                                file_path=str(file_path),
                                line_number=i,
                                code_snippet=line.strip(),
                                recommendation="Use secrets module (Python), SecureRandom (Java), or SecRandomCopyBytes (iOS)",
                                cwe_id="CWE-338",
                            )
                        )

                # Check hardcoded keys
                for pattern in self.KEY_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(
                            SASTFinding(
                                vulnerability_type=VulnerabilityType.HARDCODED_KEY,
                                severity=Severity.CRITICAL,
                                title="Hardcoded cryptographic key",
                                description="Cryptographic key is hardcoded in source code",
                                file_path=str(file_path),
                                line_number=i,
                                code_snippet=line.strip()[:100],
                                recommendation="Store keys in secure key management systems or environment variables",
                                cwe_id="CWE-321",
                                owasp_category="M10: Insufficient Cryptography",
                            )
                        )

        except (OSError, UnicodeDecodeError):
            pass

        return findings


class InsecureAPIAnalyzer:
    """
    Insecure API Usage Analyzer

    Detects usage of dangerous or deprecated APIs.
    """

    INSECURE_APIS = {
        # Python
        "eval(": ("CWE-95", Severity.CRITICAL, "Arbitrary code execution via eval()"),
        "exec(": ("CWE-95", Severity.CRITICAL, "Arbitrary code execution via exec()"),
        "compile(": ("CWE-95", Severity.HIGH, "Dynamic code compilation"),
        "pickle.load": ("CWE-502", Severity.HIGH, "Unsafe deserialization with pickle"),
        "yaml.load(": ("CWE-502", Severity.HIGH, "Unsafe YAML deserialization (use safe_load)"),
        "marshal.load": ("CWE-502", Severity.HIGH, "Unsafe deserialization with marshal"),
        "shelve.open": ("CWE-502", Severity.MEDIUM, "Shelve uses pickle internally"),
        "os.system(": ("CWE-78", Severity.HIGH, "Command injection risk with os.system"),
        "subprocess.call.*shell=True": ("CWE-78", Severity.HIGH, "Shell injection with shell=True"),
        "tempfile.mktemp": ("CWE-377", Severity.MEDIUM, "Race condition in temp file creation"),
        "assert ": ("CWE-617", Severity.LOW, "Assert can be disabled in production"),
        # Android/Java
        "setJavaScriptEnabled(true)": ("CWE-79", Severity.HIGH, "JavaScript enabled in WebView"),
        "setAllowFileAccess(true)": ("CWE-200", Severity.HIGH, "File access enabled in WebView"),
        "addJavascriptInterface": ("CWE-749", Severity.CRITICAL, "JavaScript interface injection risk"),
        "MODE_WORLD_READABLE": ("CWE-732", Severity.HIGH, "World-readable file permissions"),
        "MODE_WORLD_WRITEABLE": ("CWE-732", Severity.CRITICAL, "World-writable file permissions"),
        'allowBackup="true"': ("CWE-530", Severity.MEDIUM, "App backup enabled"),
        'debuggable="true"': ("CWE-489", Severity.CRITICAL, "Debug mode enabled"),
        'usesCleartextTraffic="true"': ("CWE-319", Severity.HIGH, "Cleartext traffic allowed"),
        "TrustManager": ("CWE-295", Severity.HIGH, "Custom TrustManager may bypass cert validation"),
        "X509TrustManager": ("CWE-295", Severity.HIGH, "Custom X509TrustManager detected"),
        "HostnameVerifier": ("CWE-297", Severity.HIGH, "Custom HostnameVerifier detected"),
        "ALLOW_ALL_HOSTNAME_VERIFIER": ("CWE-297", Severity.CRITICAL, "All hostnames accepted"),
        # iOS/Swift
        "NSAllowsArbitraryLoads": ("CWE-319", Severity.HIGH, "ATS disabled - cleartext allowed"),
        "allowsInvalidSSLCertificate": ("CWE-295", Severity.CRITICAL, "Invalid SSL certificates allowed"),
        "SecTrustSetAnchorCertificates": ("CWE-295", Severity.MEDIUM, "Custom trust anchor"),
        "kSecAttrAccessibleAlways": ("CWE-311", Severity.HIGH, "Keychain item always accessible"),
        "evaluateJavaScript": ("CWE-79", Severity.MEDIUM, "JavaScript evaluation in WebView"),
    }

    def analyze(self, file_path: Path) -> List[SASTFinding]:
        """Analyze file for insecure API usage"""
        findings = []

        try:
            content = file_path.read_text()
            lines = content.splitlines()

            for i, line in enumerate(lines, 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith(("#", "//", "/*", "*", '"""', "'''")):
                    continue

                for pattern, (cwe, severity, desc) in self.INSECURE_APIS.items():
                    # Use simple string matching for patterns without regex special chars
                    # or regex for patterns with wildcards
                    matched = False
                    if "*" in pattern or "?" in pattern or "[" in pattern:
                        # Escape parentheses for regex matching
                        escaped_pattern = pattern.replace("(", r"\(").replace(")", r"\)")
                        try:
                            matched = bool(re.search(escaped_pattern, line))
                        except re.error:
                            matched = pattern in line
                    else:
                        # Simple substring match
                        matched = pattern in line

                    if matched:
                        findings.append(
                            SASTFinding(
                                vulnerability_type=(
                                    VulnerabilityType.INSECURE_WEBVIEW
                                    if "WebView" in desc or "JavaScript" in desc
                                    else VulnerabilityType.COMMAND_INJECTION
                                ),
                                severity=severity,
                                title=f"Insecure API usage: {pattern.split('(')[0] if '(' in pattern else pattern}",
                                description=desc,
                                file_path=str(file_path),
                                line_number=i,
                                code_snippet=line.strip(),
                                cwe_id=cwe,
                            )
                        )

        except (OSError, UnicodeDecodeError):
            pass

        return findings


class AndroidManifestAnalyzer:
    """
    Android Manifest Security Analyzer

    Analyzes AndroidManifest.xml for security issues.
    """

    def analyze(self, manifest_path: Path) -> List[SASTFinding]:
        """Analyze AndroidManifest.xml"""
        findings = []

        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()

            # Namespace
            ns = {"android": "http://schemas.android.com/apk/res/android"}

            # Check application attributes
            app = root.find(".//application")
            if app is not None:
                # Debuggable
                debuggable = app.get("{http://schemas.android.com/apk/res/android}debuggable")
                if debuggable == "true":
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.DEBUGGABLE,
                            severity=Severity.CRITICAL,
                            title="Application is debuggable",
                            description="android:debuggable='true' allows debugging in production",
                            file_path=str(manifest_path),
                            line_number=1,
                            recommendation="Set android:debuggable='false' for production builds",
                            cwe_id="CWE-489",
                            owasp_category="M8: Security Misconfiguration",
                        )
                    )

                # Backup
                backup = app.get("{http://schemas.android.com/apk/res/android}allowBackup")
                if backup == "true" or backup is None:
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.BACKUP_ENABLED,
                            severity=Severity.MEDIUM,
                            title="Application backup enabled",
                            description="App data can be backed up and potentially extracted",
                            file_path=str(manifest_path),
                            line_number=1,
                            recommendation="Set android:allowBackup='false' unless explicitly needed",
                            cwe_id="CWE-530",
                            owasp_category="M9: Insecure Data Storage",
                        )
                    )

                # Cleartext traffic
                cleartext = app.get("{http://schemas.android.com/apk/res/android}usesCleartextTraffic")
                if cleartext == "true":
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.CLEARTEXT_TRANSMISSION,
                            severity=Severity.HIGH,
                            title="Cleartext traffic allowed",
                            description="Application allows unencrypted HTTP traffic",
                            file_path=str(manifest_path),
                            line_number=1,
                            recommendation="Set android:usesCleartextTraffic='false' and use HTTPS",
                            cwe_id="CWE-319",
                            owasp_category="M5: Insecure Communication",
                        )
                    )

            # Check exported components
            for component_type in ["activity", "service", "receiver", "provider"]:
                for component in root.findall(f".//{component_type}"):
                    exported = component.get("{http://schemas.android.com/apk/res/android}exported")
                    name = component.get("{http://schemas.android.com/apk/res/android}name", "unknown")

                    # Check intent filters (implicit export)
                    has_intent_filter = component.find("intent-filter") is not None

                    if exported == "true" or (has_intent_filter and exported != "false"):
                        # Check for permission protection
                        permission = component.get("{http://schemas.android.com/apk/res/android}permission")

                        if not permission:
                            findings.append(
                                SASTFinding(
                                    vulnerability_type=VulnerabilityType.INSECURE_DEEP_LINK,
                                    severity=Severity.MEDIUM,
                                    title=f"Exported {component_type} without permission",
                                    description=f"{name} is exported but not protected by permission",
                                    file_path=str(manifest_path),
                                    line_number=1,
                                    recommendation=f"Add android:permission to protect the {component_type}",
                                    cwe_id="CWE-926",
                                    owasp_category="M1: Improper Platform Usage",
                                )
                            )

            # Check dangerous permissions
            dangerous_permissions = [
                "android.permission.READ_SMS",
                "android.permission.RECEIVE_SMS",
                "android.permission.READ_CONTACTS",
                "android.permission.READ_CALL_LOG",
                "android.permission.ACCESS_FINE_LOCATION",
                "android.permission.RECORD_AUDIO",
                "android.permission.CAMERA",
            ]

            for perm in root.findall(".//uses-permission"):
                perm_name = perm.get("{http://schemas.android.com/apk/res/android}name")
                if perm_name in dangerous_permissions:
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.CLIPBOARD_DATA,
                            severity=Severity.INFO,
                            title=f"Dangerous permission: {perm_name}",
                            description=f"Application requests sensitive permission: {perm_name}",
                            file_path=str(manifest_path),
                            line_number=1,
                            recommendation="Ensure this permission is necessary and handle data securely",
                            cwe_id="CWE-250",
                        )
                    )

        except (ET.ParseError, OSError):
            pass

        return findings


class IOSPlistAnalyzer:
    """
    iOS Info.plist Security Analyzer

    Analyzes Info.plist for security issues.
    """

    def analyze(self, plist_path: Path) -> List[SASTFinding]:
        """Analyze Info.plist"""
        findings = []

        try:
            import plistlib

            with open(plist_path, "rb") as f:
                plist = plistlib.load(f)

            # Check ATS settings
            ats = plist.get("NSAppTransportSecurity", {})

            if ats.get("NSAllowsArbitraryLoads", False):
                findings.append(
                    SASTFinding(
                        vulnerability_type=VulnerabilityType.CLEARTEXT_TRANSMISSION,
                        severity=Severity.HIGH,
                        title="App Transport Security disabled",
                        description="NSAllowsArbitraryLoads allows cleartext HTTP traffic",
                        file_path=str(plist_path),
                        line_number=1,
                        recommendation="Remove NSAllowsArbitraryLoads and use HTTPS",
                        cwe_id="CWE-319",
                        owasp_category="M5: Insecure Communication",
                    )
                )

            # Check URL schemes
            url_types = plist.get("CFBundleURLTypes", [])
            for url_type in url_types:
                schemes = url_type.get("CFBundleURLSchemes", [])
                for scheme in schemes:
                    if scheme not in ["http", "https"]:
                        findings.append(
                            SASTFinding(
                                vulnerability_type=VulnerabilityType.INSECURE_DEEP_LINK,
                                severity=Severity.INFO,
                                title=f"Custom URL scheme: {scheme}",
                                description="Custom URL schemes should validate input carefully",
                                file_path=str(plist_path),
                                line_number=1,
                                recommendation="Validate all data received via URL scheme",
                                cwe_id="CWE-939",
                            )
                        )

            # Check background modes
            background_modes = plist.get("UIBackgroundModes", [])
            if "fetch" in background_modes or "remote-notification" in background_modes:
                findings.append(
                    SASTFinding(
                        vulnerability_type=VulnerabilityType.CLIPBOARD_DATA,
                        severity=Severity.INFO,
                        title="Background execution enabled",
                        description=f"App can execute in background: {background_modes}",
                        file_path=str(plist_path),
                        line_number=1,
                        recommendation="Ensure background tasks handle sensitive data securely",
                        cwe_id="CWE-200",
                    )
                )

        except (OSError, Exception):
            pass

        return findings


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
                            "name": "Observe SAST",
                            "version": "1.0.0",
                            "informationUri": "https://observe-framework.dev",
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
