"""Analyzer extracted from sast_analyzer (mechanical split; see sast/base.py)."""

import logging
import re
from pathlib import Path
from typing import Dict, List

from framework.security.sast._scan import regex_hits
from framework.security.sast.base import (
    VulnerabilityType,
    Severity,
    SASTFinding,
    default_severity_and_cwe,
)

logger = logging.getLogger(__name__)

VT = VulnerabilityType


class InsecureAPIAnalyzer:
    """
    Insecure API Usage Analyzer

    Detects usage of dangerous or deprecated APIs.
    """

    # Each entry: (VulnerabilityType, severity_override, cwe_override, description).
    # The vulnerability type is the *correct* class for the API (a TrustManager
    # is improper cert validation, not command injection). severity/cwe override
    # the per-type defaults from VULN_TYPE_DEFAULTS only when the specific API
    # warrants it; None means "inherit the canonical default".
    INSECURE_APIS = {
        # Python
        "eval(": (VT.COMMAND_INJECTION, Severity.CRITICAL, "CWE-95", "Arbitrary code execution via eval()"),
        "exec(": (VT.COMMAND_INJECTION, Severity.CRITICAL, "CWE-95", "Arbitrary code execution via exec()"),
        "compile(": (VT.COMMAND_INJECTION, None, "CWE-95", "Dynamic code compilation"),
        "pickle.load": (VT.UNSAFE_DESERIALIZATION, None, None, "Unsafe deserialization with pickle"),
        "yaml.load(": (VT.UNSAFE_DESERIALIZATION, None, None, "Unsafe YAML deserialization (use safe_load)"),
        "marshal.load": (VT.UNSAFE_DESERIALIZATION, None, None, "Unsafe deserialization with marshal"),
        "shelve.open": (VT.UNSAFE_DESERIALIZATION, Severity.MEDIUM, None, "Shelve uses pickle internally"),
        "os.system(": (VT.COMMAND_INJECTION, None, None, "Command injection risk with os.system"),
        "subprocess.call.*shell=True": (VT.COMMAND_INJECTION, None, None, "Shell injection with shell=True"),
        "tempfile.mktemp": (VT.RACE_CONDITION, None, "CWE-377", "Race condition in temp file creation"),
        "assert ": (VT.DEAD_CODE, Severity.LOW, "CWE-617", "Assert can be disabled in production"),
        # Android/Java
        "setJavaScriptEnabled(true)": (VT.INSECURE_WEBVIEW, None, "CWE-79", "JavaScript enabled in WebView"),
        "setAllowFileAccess(true)": (VT.INSECURE_WEBVIEW, None, "CWE-200", "File access enabled in WebView"),
        "addJavascriptInterface": (VT.INSECURE_WEBVIEW, Severity.CRITICAL, None, "JavaScript interface injection risk"),
        "MODE_WORLD_READABLE": (VT.INSECURE_STORAGE, Severity.HIGH, "CWE-732", "World-readable file permissions"),
        "MODE_WORLD_WRITEABLE": (VT.INSECURE_STORAGE, Severity.CRITICAL, "CWE-732", "World-writable file permissions"),
        'allowBackup="true"': (VT.BACKUP_ENABLED, None, None, "App backup enabled"),
        'debuggable="true"': (VT.DEBUGGABLE, None, None, "Debug mode enabled"),
        'usesCleartextTraffic="true"': (VT.CLEARTEXT_TRANSMISSION, None, None, "Cleartext traffic allowed"),
        "TrustManager": (VT.IMPROPER_CERT_VALIDATION, None, None, "Custom TrustManager may bypass cert validation"),
        "X509TrustManager": (VT.IMPROPER_CERT_VALIDATION, None, None, "Custom X509TrustManager detected"),
        "HostnameVerifier": (VT.IMPROPER_CERT_VALIDATION, None, "CWE-297", "Custom HostnameVerifier detected"),
        "ALLOW_ALL_HOSTNAME_VERIFIER": (
            VT.IMPROPER_CERT_VALIDATION,
            Severity.CRITICAL,
            "CWE-297",
            "All hostnames accepted",
        ),
        # iOS/Swift
        "NSAllowsArbitraryLoads": (VT.CLEARTEXT_TRANSMISSION, None, None, "ATS disabled - cleartext allowed"),
        "allowsInvalidSSLCertificate": (
            VT.IMPROPER_CERT_VALIDATION,
            Severity.CRITICAL,
            None,
            "Invalid SSL certificates allowed",
        ),
        "SecTrustSetAnchorCertificates": (VT.IMPROPER_CERT_VALIDATION, Severity.MEDIUM, None, "Custom trust anchor"),
        "kSecAttrAccessibleAlways": (VT.INSECURE_STORAGE, Severity.HIGH, "CWE-311", "Keychain item always accessible"),
        "evaluateJavaScript": (VT.INSECURE_WEBVIEW, Severity.MEDIUM, "CWE-79", "JavaScript evaluation in WebView"),
    }

    # Regex rules as ordered pattern STRINGS (substrings become re.escape'd exact matches;
    # wildcard rules keep their paren-escaped regex), so the whole set matches in ONE
    # case-sensitive RegexSet pass via native.scan_lines instead of a search per rule per line.
    _patterns: "List[str] | None" = None
    _metas: "List[tuple] | None" = None

    @classmethod
    def _rules(cls) -> "tuple[list, list]":
        """(ordered pattern strings, [(original_pattern, meta)]), built once and cached."""
        pats, metas = cls._patterns, cls._metas
        if pats is None or metas is None:
            pats, metas = [], []
            for pattern, meta in cls.INSECURE_APIS.items():
                if "*" in pattern or "?" in pattern or "[" in pattern:
                    pat = pattern.replace("(", r"\(").replace(")", r"\)")
                else:
                    pat = re.escape(pattern)  # exact substring, as a regex
                pats.append(pat)
                metas.append((pattern, meta))
            cls._patterns, cls._metas = pats, metas
        return pats, metas

    def _findings(self, file_path: str, content: str, hits: Dict[int, set]) -> List[SASTFinding]:
        """Build findings for one file from its precomputed hits (``{line: {rule_idx}}``). Same
        emission as the per-line scan: comment lines are skipped whole, matched rules emit in
        rule order — so the batched path yields exactly the same findings as ``analyze``."""
        _pats, metas = self._rules()
        findings: List[SASTFinding] = []
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", "//", "/*", "*", '"""', "'''")):
                continue  # comment line — no findings
            line_hits = hits.get(i, ())
            if not line_hits:
                continue
            for ri in range(len(metas)):
                if ri in line_hits:
                    pattern, (vuln_type, severity_override, cwe_override, desc) = metas[ri]
                    default_severity, default_cwe = default_severity_and_cwe(vuln_type)
                    findings.append(
                        SASTFinding(
                            vulnerability_type=vuln_type,
                            severity=severity_override or default_severity,
                            title=f"Insecure API usage: {pattern.split('(')[0] if '(' in pattern else pattern}",
                            description=desc,
                            file_path=file_path,
                            line_number=i,
                            code_snippet=line.strip(),
                            cwe_id=cwe_override or default_cwe,
                        )
                    )
        return findings

    def analyze(self, file_path: Path) -> List[SASTFinding]:
        """Analyze one file for insecure API usage."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.debug("SAST insecure-api: skipped %s: %s", file_path, e)
            return []
        hits = regex_hits([content], self._rules()[0], False)[0]
        return self._findings(str(file_path), content, hits)

    def analyze_files(self, files: List["tuple[Path, str]"]) -> List[SASTFinding]:
        """Batch many ``(path, content)`` through ONE native.scan_lines call (RegexSet, parallel
        over files); identical findings to calling :meth:`analyze` on each, but one pass total."""
        contents = [content for _path, content in files]
        per_file = regex_hits(contents, self._rules()[0], False)
        out: List[SASTFinding] = []
        for (path, content), hits in zip(files, per_file):
            out.extend(self._findings(str(path), content, hits))
        return out
