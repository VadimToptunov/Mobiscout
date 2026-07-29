"""Canonical secret / PII detection patterns for the security subsystem.

Historically the same secret- and PII-detection regexes were re-implemented in
about six modules (the scanner, the config validator, the APK/binary
decompilers, the advanced secrets scanner and the DAST traffic analyzer) with
divergent quality — three of them even carried a buggy ``[A-Z|a-z]`` email
character class (which quietly also matches a literal ``|``).

This module is the single source of truth. It exposes:

* atomic named regex constants (the *union* of every pattern used across the
  subsystem — deduplicated where the regex text was identical, and with the
  email class fixed to ``[A-Za-z]`` in the one place it now lives), and
* per-caller pattern *groups* (dicts / spec lists) that preserve each caller's
  exact category labels and finding shape, and
* a placeholder / false-positive helper shared by the callers that need it.

Nothing here changes what any caller emits: callers keep their own finding
construction and category names, they simply source the regex text from here.
"""

import re
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
# Atomic patterns — shared across multiple callers (identical text collapsed).
# --------------------------------------------------------------------------- #
URL = r'https?://[^\s"\'<>]+'
IPV4 = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
# Fixed email class: the historical ``[A-Z|a-z]`` also matched a literal ``|``.
EMAIL = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
AWS_ACCESS_KEY_ID = r"AKIA[0-9A-Z]{16}"
GOOGLE_API_KEY = r"AIza[0-9A-Za-z\-_]{35}"
FIREBASE_DB_URL = r"[a-z0-9-]+\.firebaseio\.com"
JWT = r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+"
SQL_QUERY = r"(?:SELECT|INSERT|UPDATE|DELETE)\s+.+\s+(?:FROM|INTO|SET)"
CREDIT_CARD = r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
SSN = r"\b\d{3}-\d{2}-\d{4}\b"

# --------------------------------------------------------------------------- #
# Assignment-style (labelled) secret patterns.
# --------------------------------------------------------------------------- #
# ``password = "..."`` style, key/value form. Shared by the APK decompiler and
# the generic string extractor.
PASSWORD_ASSIGNMENT = r'(?:password|passwd|pwd)["\s:=]+["\']?([^\s"\']{4,})["\']?'
# ``api_key = "..."`` with an explicit ``api_secret`` alias and a 20-char floor
# (APK decompiler).
API_KEY_ASSIGNMENT = r'(?:api[_-]?key|apikey|api_secret)["\s:=]+["\']?([\w\-]{20,})["\']?'
# Same idea with a 16-char floor and no ``api_secret`` alias (string extractor).
API_KEY_ASSIGNMENT_16 = r'(?:api[_-]?key|apikey)["\s:=]+["\']?([\w\-]{16,})["\']?'
# ``token``/``secret`` key/value (string extractor).
TOKEN_ASSIGNMENT = r'(?:token|secret)["\s:=]+["\']?([\w\-]{16,})["\']?'
# Word-boundary-anchored api-key variant used over network traffic (DAST).
DAST_API_KEY = r'\b(?:api[_-]?key|apikey|api_secret)["\s:=]+["\']?[\w\-]{20,}["\']?'
# Credentials leaked through a URL query string (DAST).
PASSWORD_IN_URL = r"[?&](?:password|passwd|pwd|pass)=([^&\s]+)"
# ``Authorization: Bearer <token>`` header value (DAST).
BEARER_TOKEN_HEADER = r"Bearer\s+[\w\-\.]+"

# --------------------------------------------------------------------------- #
# PEM private-key headers — three historical variants, kept distinct because
# they match subtly different key types (collapsing them would change matches).
# --------------------------------------------------------------------------- #
PRIVATE_KEY_APK = r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"
PRIVATE_KEY_SCANNER = r"-----BEGIN (RSA|DSA|EC) PRIVATE KEY-----"
PRIVATE_KEY_CONFIG = r"-----BEGIN (?:RSA|DSA|EC) PRIVATE KEY-----"

# --------------------------------------------------------------------------- #
# Scanner- / config-specific quoted-literal patterns.
# --------------------------------------------------------------------------- #
SCANNER_API_KEY = r"api[_-]?key['\"]?\s*[:=]\s*['\"][a-zA-Z0-9]{20,}['\"]"
SCANNER_PASSWORD = r"password['\"]?\s*[:=]\s*['\"][^'\"]{8,}['\"]"
CONFIG_API_KEY = r'["\']([A-Za-z0-9]{32,})["\']'
CONFIG_PASSWORD = r'password\s*=\s*["\'](?!.*env|.*config)[^"\']{8,}["\']'
CONFIG_TOKEN = r'token\s*=\s*["\'][A-Za-z0-9_-]{20,}["\']'

# --------------------------------------------------------------------------- #
# Per-caller pattern groups. Each preserves its caller's exact category labels
# and ordering so the finding shape is unchanged.
# --------------------------------------------------------------------------- #

# framework/security/scanner.py :: AndroidSecurityScanner._check_hardcoded_secrets
SCANNER_SECRET_PATTERNS: Dict[str, str] = {
    "API Key": SCANNER_API_KEY,
    "AWS Key": AWS_ACCESS_KEY_ID,
    "Private Key": PRIVATE_KEY_SCANNER,
    "Password": SCANNER_PASSWORD,
}

# framework/security/config.py :: validate_no_hardcoded_secrets
CONFIG_SECRET_PATTERNS: Dict[str, str] = {
    "Potential API Key": CONFIG_API_KEY,
    "Potential AWS Key": AWS_ACCESS_KEY_ID,
    "Potential Private Key": PRIVATE_KEY_CONFIG,
    "Hardcoded Password": CONFIG_PASSWORD,
    "Potential Token": CONFIG_TOKEN,
}

# framework/security/decompile/apk.py :: APKDecompiler.SENSITIVE_PATTERNS
DECOMPILE_SENSITIVE_PATTERNS: Dict[str, str] = {
    "url": URL,
    "ip_address": IPV4,
    "api_key": API_KEY_ASSIGNMENT,
    "aws_key": AWS_ACCESS_KEY_ID,
    "google_api": GOOGLE_API_KEY,
    "firebase": FIREBASE_DB_URL,
    "password": PASSWORD_ASSIGNMENT,
    "private_key": PRIVATE_KEY_APK,
    "jwt": JWT,
    "sql_query": SQL_QUERY,
}

# framework/security/decompile/orchestrator.py :: Decompiler._extract_strings_from_bytes
EXTRACT_STRING_PATTERNS: Dict[str, str] = {
    "url": URL,
    "ip_address": IPV4,
    "api_key": API_KEY_ASSIGNMENT_16,
    "email": EMAIL,
    "password": PASSWORD_ASSIGNMENT,
    "token": TOKEN_ASSIGNMENT,
}

# framework/security/dast/traffic.py :: NetworkTrafficAnalyzer.SENSITIVE_PATTERNS
DAST_SENSITIVE_PATTERNS: Dict[str, str] = {
    "credit_card": CREDIT_CARD,
    "ssn": SSN,
    "email": EMAIL,
    "api_key": DAST_API_KEY,
    "jwt": JWT,
    "password_in_url": PASSWORD_IN_URL,
    "bearer_token": BEARER_TOKEN_HEADER,
}

# framework/security/advanced/secrets.py :: HardcodedSecretsScanner._initialize_patterns
# Spec tuples: (name, regex, risk_level_name, entropy_threshold). The scanner
# maps ``risk_level_name`` onto its RiskLevel enum so this module stays free of
# any dependency on the advanced package.
ADVANCED_SECRET_SPECS: List[Tuple[str, str, str, float]] = [
    # AWS
    ("AWS Access Key ID", r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}", "CRITICAL", 4.0),
    (
        "AWS Secret Access Key",
        r'(?:aws)?[_\-]?secret[_\-]?(?:access)?[_\-]?key["\'\s:=]+[A-Za-z0-9/+=]{40}',
        "CRITICAL",
        4.5,
    ),
    # Google
    ("Google API Key", GOOGLE_API_KEY, "HIGH", 4.0),
    ("Google OAuth Client ID", r"[0-9]+-[a-z0-9_]{32}\.apps\.googleusercontent\.com", "MEDIUM", 3.5),
    (
        "Firebase API Key",
        r'(?:firebase|FIREBASE)[_\-]?(?:API)?[_\-]?KEY["\'\s:=]+[A-Za-z0-9\-_]{39}',
        "HIGH",
        4.0,
    ),
    # GitHub
    ("GitHub Token", r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}", "CRITICAL", 4.5),
    ("GitHub OAuth", r'github[_\-]?(?:oauth)?[_\-]?(?:token|secret)["\'\s:=]+[A-Za-z0-9_]{40}', "CRITICAL", 4.0),
    # Stripe
    ("Stripe API Key", r"(?:sk|pk)_(?:test|live)_[A-Za-z0-9]{24,}", "CRITICAL", 4.5),
    # Twilio
    ("Twilio API Key", r"SK[a-f0-9]{32}", "HIGH", 4.0),
    ("Twilio Auth Token", r'twilio[_\-]?auth[_\-]?token["\'\s:=]+[a-f0-9]{32}', "HIGH", 4.0),
    # Slack
    ("Slack Token", r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*", "HIGH", 4.0),
    (
        "Slack Webhook",
        r"https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[A-Za-z0-9]{24}",
        "MEDIUM",
        3.5,
    ),
    # Generic tokens and keys
    ("Generic API Key", r'(?:api[_\-]?key|apikey)["\'\s:=]+[A-Za-z0-9\-_]{20,}', "HIGH", 3.5),
    ("Generic Secret", r'(?:secret|SECRET)[_\-]?(?:KEY|key)?["\'\s:=]+[A-Za-z0-9\-_/+=]{16,}', "HIGH", 4.0),
    ("Bearer Token", r"[Bb]earer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+", "HIGH", 4.0),
    # Private keys (no entropy check needed)
    ("RSA Private Key", r"-----BEGIN (?:RSA )?PRIVATE KEY-----", "CRITICAL", 0.0),
    ("EC Private Key", r"-----BEGIN EC PRIVATE KEY-----", "CRITICAL", 0.0),
    ("PGP Private Key", r"-----BEGIN PGP PRIVATE KEY BLOCK-----", "CRITICAL", 0.0),
    # Database
    (
        "Database Connection String",
        r'(?:mongodb|mysql|postgres|redis)://[^"\'\s]+:[^"\'\s]+@[^"\'\s]+',
        "CRITICAL",
        3.0,
    ),
    # Passwords
    ("Password in Code", r'(?:password|passwd|pwd)["\'\s:=]+["\'][^"\']{8,}["\']', "HIGH", 3.0),
    # JWT
    ("JWT Token", JWT, "MEDIUM", 4.0),
    # Mobile-specific
    ("Google Maps API Key", r"AIza[0-9A-Za-z\\-_]{35}", "MEDIUM", 4.0),
    ("Facebook App Secret", r'(?:facebook|fb)[_\-]?(?:app)?[_\-]?secret["\'\s:=]+[a-f0-9]{32}', "HIGH", 4.0),
]

# --------------------------------------------------------------------------- #
# Placeholder / false-positive helpers.
# --------------------------------------------------------------------------- #

# Obvious non-secret placeholder values (test data, fuzz labels, docs) that must
# never be reported as leaked credentials. Matched by *exact value*.
PLACEHOLDER_VALUES = frozenset(
    {
        "password",
        "wrong_password",
        "changeme",
        "placeholder",
        "your_password",
        "test_password",
        "dummy",
        "example",
        "sample",
        "redacted",
    }
)

# Token indicators for obvious non-secrets (test fixtures, placeholders).
# Matched on WORD BOUNDARIES so a genuine secret sitting next to words like
# "latest"/"manifest"/"greatest" is not silently dropped.
TOKEN_FP_PATTERN = re.compile(
    r"\b(?:example|test|sample|demo|fake|mock|placeholder|dummy)\b|\bx{3,}|\byour[_-]?",
    re.I,
)

# Structural placeholders (never a real secret regardless of context).
STRUCTURAL_FP_PATTERNS = [
    re.compile(r"<[^>]+>"),  # XML/HTML placeholders
    re.compile(r"\$\{[^}]+\}"),  # Variable substitution
    re.compile(r"%[sd]"),  # Format strings
]


def is_placeholder_value(value: str) -> bool:
    """Return True when ``value`` is an obvious non-secret placeholder token."""
    return value.lower() in PLACEHOLDER_VALUES


def is_false_positive(match: str, context: str) -> bool:
    """Return True when a matched secret is likely a false positive.

    Token indicators ("test", "demo", ...) are matched on word boundaries so an
    unrelated longer word ("latest", "manifest", "greatest") near a real secret
    does not suppress it. ``context`` is expected to be a narrow window around
    the match, not a wide span.
    """
    if TOKEN_FP_PATTERN.search(match) or TOKEN_FP_PATTERN.search(context):
        return True

    for fp_pattern in STRUCTURAL_FP_PATTERNS:
        if fp_pattern.search(match) or fp_pattern.search(context):
            return True

    return False
