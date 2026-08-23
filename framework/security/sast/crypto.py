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
)

logger = logging.getLogger(__name__)


class CryptoAnalyzer:
    """
    Cryptographic Weakness Analyzer

    Detects insecure cryptographic implementations.
    """

    # Weak algorithms
    WEAK_ALGORITHMS = {
        "MD5": ("CWE-327", "MD5 is cryptographically broken"),
        "SHA1": ("CWE-327", "SHA1 is considered weak for security purposes"),
        # (SHA1 uses a custom match pattern below to also catch SHA-1 / SHA_1.)
        "DES": ("CWE-327", "DES has insufficient key length"),
        "3DES": ("CWE-327", "Triple DES is deprecated"),
        "RC4": ("CWE-327", "RC4 has multiple vulnerabilities"),
        "RC2": ("CWE-327", "RC2 is considered weak"),
        "Blowfish": ("CWE-327", "Blowfish with small key sizes is weak"),
        "ECB": ("CWE-327", "ECB mode doesn't provide semantic security"),
    }

    # Match-pattern overrides for algorithms whose written form varies. Without
    # this, `\bSHA1\b` misses the common "SHA-1" / "SHA_1" / "SHA 1" spellings.
    ALGO_PATTERN_OVERRIDES = {
        "SHA1": r"\bSHA[-_ ]?1\b",
    }

    # Insecure random. NB: arc4random / arc4random_uniform are intentionally
    # excluded — on Apple platforms they are backed by a CSPRNG, so flagging
    # them produced false positives.
    INSECURE_RANDOM = [
        "random.random",
        "random.randint",
        "random.choice",
        "Math.random",
        "java.util.Random",
    ]

    # Hardcoded key patterns
    KEY_PATTERNS = [
        r'["\']?(?:aes|des|rsa|hmac)?[_-]?(?:key|secret|password)["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
        r'(?:private|secret|encryption)[_-]?key\s*=\s*["\'][^"\']+["\']',
        r'iv\s*=\s*["\'][0-9a-fA-F]{16,}["\']',
        r'nonce\s*=\s*["\'][0-9a-fA-F]+["\']',
    ]

    # Regex rules as ordered pattern STRINGS, so the whole scan runs through ONE batched
    # native.scan_lines call (RegexSet — one pass, files in parallel) instead of a re.search
    # per rule per line. Indices 0..len(algos)-1 are the weak-algorithm rules; the remaining
    # indices are the hardcoded-key rules. Built once and cached on the class.
    _patterns: "List[str] | None" = None
    _algo_meta: "List[tuple] | None" = None

    @classmethod
    def _rules(cls) -> "tuple[list, list]":
        """(ordered pattern strings, algo metadata). Algo rules come first, then key rules."""
        pats, meta = cls._patterns, cls._algo_meta
        if pats is None or meta is None:
            meta = [(a, cwe, desc) for a, (cwe, desc) in cls.WEAK_ALGORITHMS.items()]
            algo_pats = [cls.ALGO_PATTERN_OVERRIDES.get(a, rf"\b{re.escape(a)}\b") for a, _cwe, _d in meta]
            pats = algo_pats + list(cls.KEY_PATTERNS)
            cls._patterns, cls._algo_meta = pats, meta
        return pats, meta

    def _findings(self, file_path: str, content: str, hits: Dict[int, set]) -> List[SASTFinding]:
        """Build findings for one file from its precomputed regex hits (``{line: {rule_idx}}``)
        plus the inline case-insensitive substring insecure-random check. The emission order is
        identical to the per-line scan: weak-algorithm, then insecure-random, then hardcoded-key,
        in line order — so the batched path yields exactly the same findings as ``analyze``."""
        _pats, meta = self._rules()
        n_algo = len(meta)
        findings: List[SASTFinding] = []
        for i, line in enumerate(content.splitlines(), 1):
            line_hits = hits.get(i, ())
            lower_line = line.lower()

            # Weak algorithms (word-boundary regex). A match inside a comment is not a real use.
            for ai in range(n_algo):
                if ai in line_hits:
                    stripped = line.strip()
                    if stripped.startswith(("#", "//", "/*", "*")):
                        continue
                    algo, cwe, desc = meta[ai]
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.WEAK_CRYPTO,
                            severity=Severity.HIGH,
                            title=f"Weak cryptographic algorithm: {algo}",
                            description=desc,
                            file_path=file_path,
                            line_number=i,
                            code_snippet=line.strip(),
                            recommendation=f"Replace {algo} with a stronger algorithm (AES-256, SHA-256, etc.)",
                            cwe_id=cwe,
                            owasp_category="M5: Insufficient Cryptography",
                        )
                    )

            # Insecure random (case-insensitive substring — kept inline, not a regex rule).
            for pattern in self.INSECURE_RANDOM:
                if pattern.lower() in lower_line:
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.INSECURE_RANDOM,
                            severity=Severity.MEDIUM,
                            title="Insecure random number generator",
                            description=f"'{pattern}' is not cryptographically secure",
                            file_path=file_path,
                            line_number=i,
                            code_snippet=line.strip(),
                            recommendation="Use secrets module (Python), SecureRandom (Java), or SecRandomCopyBytes (iOS)",
                            cwe_id="CWE-338",
                        )
                    )

            # Hardcoded keys (regex rules, indices after the algo rules).
            for ki in range(len(self.KEY_PATTERNS)):
                if (n_algo + ki) in line_hits:
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.HARDCODED_KEY,
                            severity=Severity.CRITICAL,
                            title="Hardcoded cryptographic key",
                            description="Cryptographic key is hardcoded in source code",
                            file_path=file_path,
                            line_number=i,
                            code_snippet=line.strip()[:100],
                            recommendation="Store keys in secure key management systems or environment variables",
                            cwe_id="CWE-321",
                            owasp_category="M10: Insufficient Cryptography",
                        )
                    )
        return findings

    def analyze(self, file_path: Path) -> List[SASTFinding]:
        """Analyze one file for cryptographic weaknesses."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.debug("SAST crypto: skipped %s: %s", file_path, e)
            return []
        hits = regex_hits([content], self._rules()[0], True)[0]
        return self._findings(str(file_path), content, hits)

    def analyze_files(self, files: List["tuple[Path, str]"]) -> List[SASTFinding]:
        """Batch many ``(path, content)`` through ONE native.scan_lines call (RegexSet, parallel
        over files); identical findings to calling :meth:`analyze` on each, but one pass total."""
        contents = [content for _path, content in files]
        per_file = regex_hits(contents, self._rules()[0], True)
        out: List[SASTFinding] = []
        for (path, content), hits in zip(files, per_file):
            out.extend(self._findings(str(path), content, hits))
        return out
