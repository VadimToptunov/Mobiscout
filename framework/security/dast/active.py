"""Active API security probing (#314) — the real checks behind ``APISecurityTester``.

This module issues real HTTP requests to a target, so it is **off by default and gated**:
nothing here runs unless the caller passes ``active=True`` AND ``authorized=True`` (the CLI
maps those to ``--active`` plus an explicit authorization confirmation). Without both, the
caller keeps returning the honest "not tested" INFO finding. Every request also goes through
a rate limiter so a scan can't hammer the target.

What it checks per endpoint: reflected injection (SQLi / XSS / path traversal) by error and
reflection signatures against a benign baseline, authentication bypass (a protected endpoint
answering the same without / with a tampered token), whether any rate limiting is observed,
and permissive CORS. Findings carry severity, evidence and a recommendation.

Transport is injected (``transport=``) so tests drive it against a local mock server with no
sockets of their own; the default uses the standard library only (no new dependency).
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from framework.security.dast.base import DASTFinding, DASTSeverity, DASTTestType

#: A value no clean endpoint echoes back, so a reflection is unambiguously ours.
_MARKER = "mbz9x1"
#: Reflected-XSS probe: if this exact (unescaped) string comes back in an HTML response, the
#: endpoint reflects markup without encoding it.
_XSS_PROBE = f"<{_MARKER}>"
#: SQL injection probe: an unbalanced quote, which an unparameterised query turns into a DB error.
_SQLI_PROBE = "'"
#: Path-traversal probe and the signatures a successful read of a well-known file leaves.
_TRAVERSAL_PROBE = "../../../../etc/passwd"
_TRAVERSAL_SIGNATURES = ("root:x:0:0", "root:*:0:0", "[extensions]")
#: Substrings of common SQL driver error messages (lower-cased match).
_SQL_ERROR_SIGNATURES = (
    "sql syntax",
    "syntax error at or near",
    "unclosed quotation mark",
    "sqlite3.operationalerror",
    "sqlite_error",
    "psycopg2",
    "you have an error in your sql",
    "ora-00933",
    "odbc sql server driver",
    "pg::syntaxerror",
)
#: An origin no legitimate CORS policy should trust — used to detect reflect-any-origin.
_EVIL_ORIGIN = "https://evil.example"


@dataclass
class Response:
    """What the transport returns for one request."""

    status: int
    body: str
    headers: Dict[str, str]
    elapsed_ms: float = 0.0

    def header(self, name: str) -> Optional[str]:
        """Case-insensitive header lookup (HTTP header names are case-insensitive)."""
        lowered = name.lower()
        return next((v for k, v in self.headers.items() if k.lower() == lowered), None)


class ActiveScanNotAuthorizedError(RuntimeError):
    """Raised when an active scan is requested without an explicit authorization acknowledgement.

    Active scanning sends attack traffic to the target, which is only lawful against a system
    you own or have written permission to test — so the scanner refuses to start rather than
    assume consent."""


Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Response]


def urllib_transport(timeout: float = 10.0) -> Transport:
    """The default transport: one real HTTP request via the standard library, no dependency.

    A non-2xx status is a normal result here (an error page is evidence), so ``HTTPError`` —
    which is itself a response — is read like any other instead of raising."""

    def send(method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> Response:
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        started = time.monotonic()
        try:
            raw = urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 — caller-authorized target
        except urllib.error.HTTPError as http_error:
            raw = http_error  # an HTTPError exposes .status/.read()/.headers like a response
        with raw:
            body = raw.read().decode("utf-8", "replace")
            elapsed = (time.monotonic() - started) * 1000
            return Response(status=int(raw.status or 0), body=body, headers=dict(raw.headers), elapsed_ms=elapsed)

    return send


class _RateLimiter:
    """A minimum interval between requests (``requests_per_second``), so a scan can't flood the
    target. ``requests_per_second <= 0`` disables the wait."""

    def __init__(self, requests_per_second: float, sleep: Callable[[float], None] = time.sleep) -> None:
        self._min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._sleep = sleep
        self._last = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        gap = self._min_interval - (now - self._last)
        if gap > 0:
            self._sleep(gap)
        self._last = time.monotonic()


class ActiveAPIScanner:
    """Runs the active checks against one endpoint. Construct per scan; it holds the transport,
    the rate limiter and the request counter used to report scan volume."""

    def __init__(
        self,
        *,
        authorized: bool,
        rate_limit_rps: float = 5.0,
        transport: Optional[Transport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not authorized:
            raise ActiveScanNotAuthorizedError(
                "Active API scanning sends attack traffic to the target and must be explicitly "
                "authorized (active=True requires authorized=True / the CLI's authorization prompt)."
            )
        self._transport = transport or urllib_transport()
        self._rate = _RateLimiter(rate_limit_rps, sleep=sleep)
        self.requests_made = 0

    def _request(
        self, method: str, url: str, headers: Optional[Dict[str, str]] = None, data: Optional[bytes] = None
    ) -> Response:
        self._rate.wait()
        self.requests_made += 1
        return self._transport(method, url, dict(headers or {}), data)

    def scan_endpoint(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> List[DASTFinding]:
        """Probe one endpoint and return the confirmed findings (empty when it looks clean)."""
        headers = dict(headers or {})
        params = dict(params or {})
        findings: List[DASTFinding] = []
        findings.extend(self._injection_checks(url, method, headers, params))
        findings.extend(self._auth_bypass_check(url, method, headers, params))
        findings.extend(self._rate_limit_check(url, method, headers, params))
        findings.extend(self._cors_check(url, method, headers))
        for finding in findings:
            finding.endpoint = finding.endpoint or urllib.parse.urlsplit(url).path
            finding.method = finding.method or method
        return findings

    def _send_with_params(self, url: str, method: str, headers: Dict[str, str], params: Dict[str, str]) -> Response:
        """A request carrying ``params`` — in the query string for GET, form-encoded body otherwise."""
        encoded = urllib.parse.urlencode(params)
        if method.upper() == "GET":
            target = url + (("&" if urllib.parse.urlsplit(url).query else "?") + encoded if encoded else "")
            return self._request(method, target, headers)
        body = encoded.encode()
        form_headers = {**headers, "Content-Type": "application/x-www-form-urlencoded"}
        return self._request(method, url, form_headers, body)

    def _injection_checks(
        self, url: str, method: str, headers: Dict[str, str], params: Dict[str, str]
    ) -> List[DASTFinding]:
        """Substitute each injection probe into each parameter and look for the matching signature.

        An endpoint with no parameters can't be fuzzed this way, so nothing is reported for it
        (rather than a false 'secure')."""
        findings: List[DASTFinding] = []
        for name in params:
            findings.extend(self._probe_param(url, method, headers, params, name))
        return findings

    def _probe_param(
        self, url: str, method: str, headers: Dict[str, str], params: Dict[str, str], name: str
    ) -> List[DASTFinding]:
        findings: List[DASTFinding] = []
        for probe, detector, build in _PARAM_PROBES:
            mutated = {**params, name: build(params[name])}
            response = self._send_with_params(url, method, headers, mutated)
            finding = detector(self, name, probe, response)
            if finding is not None:
                findings.append(finding)
        return findings

    def _detect_sqli(self, name: str, probe: str, response: Response) -> Optional[DASTFinding]:
        hit = next((s for s in _SQL_ERROR_SIGNATURES if s in response.body.lower()), None)
        if hit is None:
            return None
        return DASTFinding(
            test_type=DASTTestType.INJECTION,
            severity=DASTSeverity.CRITICAL,
            title="SQL injection",
            description=f"Parameter '{name}' returned a SQL error when sent a single quote, indicating the value "
            "reaches an unparameterised query.",
            evidence=f"'{name}={probe}' -> {response.status}, SQL error signature '{hit}' in response",
            recommendation="Use parameterised queries / prepared statements; never build SQL by string concatenation.",
            cwe_id="CWE-89",
            owasp_category="A03:2021 Injection",
            vulnerability_type="sql_injection",
        )

    def _detect_xss(self, name: str, probe: str, response: Response) -> Optional[DASTFinding]:
        content_type = (response.header("Content-Type") or "").lower()
        if _XSS_PROBE not in response.body or "html" not in content_type:
            return None
        return DASTFinding(
            test_type=DASTTestType.INJECTION,
            severity=DASTSeverity.HIGH,
            title="Reflected cross-site scripting (XSS)",
            description=f"Parameter '{name}' is reflected into an HTML response without encoding, so a crafted "
            "value is interpreted as markup.",
            evidence=f"'{name}={probe}' reflected verbatim in a text/html response",
            recommendation="Context-encode all user input on output; set a restrictive Content-Security-Policy.",
            cwe_id="CWE-79",
            owasp_category="A03:2021 Injection",
            vulnerability_type="reflected_xss",
        )

    def _detect_traversal(self, name: str, probe: str, response: Response) -> Optional[DASTFinding]:
        hit = next((s for s in _TRAVERSAL_SIGNATURES if s in response.body), None)
        if hit is None:
            return None
        return DASTFinding(
            test_type=DASTTestType.INJECTION,
            severity=DASTSeverity.CRITICAL,
            title="Path traversal",
            description=f"Parameter '{name}' can reach files outside the intended directory; a traversal sequence "
            "returned the contents of a system file.",
            evidence=f"'{name}={probe}' returned a system-file signature '{hit}'",
            recommendation="Resolve and confine paths to an allow-listed base directory; reject '..' segments.",
            cwe_id="CWE-22",
            owasp_category="A01:2021 Broken Access Control",
            vulnerability_type="path_traversal",
        )

    def _auth_bypass_check(
        self, url: str, method: str, headers: Dict[str, str], params: Dict[str, str]
    ) -> List[DASTFinding]:
        """If the caller supplied an Authorization header, the endpoint is meant to be protected.
        Re-request it without that header and with a tampered token; a 2xx either way means the
        protection isn't enforced."""
        auth_key = next((k for k in headers if k.lower() == "authorization"), None)
        if auth_key is None:
            return []
        authed = self._send_with_params(url, method, headers, params)
        if not _is_success(authed.status):
            return []  # can't conclude anything if the authorized call itself didn't succeed
        for label, mutated in (
            ("no Authorization header", {k: v for k, v in headers.items() if k != auth_key}),
            ("a tampered token", {**headers, auth_key: headers[auth_key] + "tampered"}),
        ):
            response = self._send_with_params(url, method, mutated, params)
            if _is_success(response.status):
                return [
                    DASTFinding(
                        test_type=DASTTestType.AUTHENTICATION,
                        severity=DASTSeverity.HIGH,
                        title="Authentication bypass",
                        description="A protected endpoint returned a success response when called with "
                        f"{label}, so authentication is not enforced server-side.",
                        evidence=f"Authorized request -> {authed.status}; with {label} -> {response.status}",
                        recommendation="Enforce authentication on the server for every protected route; "
                        "reject missing or invalid tokens with 401.",
                        cwe_id="CWE-287",
                        owasp_category="A07:2021 Identification and Authentication Failures",
                        vulnerability_type="auth_bypass",
                    )
                ]
        return []

    def _rate_limit_check(
        self, url: str, method: str, headers: Dict[str, str], params: Dict[str, str]
    ) -> List[DASTFinding]:
        """Fire a short burst; if the server never answers 429, note that no rate limiting is
        observed. This is informational (absence of evidence), not a confirmed vulnerability."""
        statuses = [self._send_with_params(url, method, headers, params).status for _ in range(_RATE_BURST)]
        if any(status == 429 for status in statuses):
            return []
        return [
            DASTFinding(
                test_type=DASTTestType.API,
                severity=DASTSeverity.LOW,
                title="No rate limiting observed",
                description=f"{_RATE_BURST} rapid requests all succeeded without a 429 response; the endpoint may "
                "lack rate limiting, easing brute-force and scraping.",
                evidence=f"{_RATE_BURST} requests, statuses {sorted(set(statuses))}, no 429",
                recommendation="Apply per-client rate limiting and return 429 with Retry-After when it is exceeded.",
                cwe_id="CWE-770",
                owasp_category="A04:2021 Insecure Design",
                vulnerability_type="missing_rate_limit",
            )
        ]

    def _cors_check(self, url: str, method: str, headers: Dict[str, str]) -> List[DASTFinding]:
        """Ask with a hostile Origin; a policy that reflects it (or allows any origin together with
        credentials) lets any site read authenticated responses."""
        response = self._request(method, url, {**headers, "Origin": _EVIL_ORIGIN})
        allow_origin = response.header("Access-Control-Allow-Origin")
        if allow_origin is None:
            return []
        allows_credentials = (response.header("Access-Control-Allow-Credentials") or "").lower() == "true"
        reflects_origin = allow_origin in (_EVIL_ORIGIN, "*")
        if not reflects_origin:
            return []
        severity = DASTSeverity.HIGH if allows_credentials else DASTSeverity.MEDIUM
        with_creds = " together with Access-Control-Allow-Credentials: true" if allows_credentials else ""
        return [
            DASTFinding(
                test_type=DASTTestType.API,
                severity=severity,
                title="Permissive CORS policy",
                description=f"The endpoint returned Access-Control-Allow-Origin: {allow_origin}{with_creds}, letting "
                "untrusted origins read its responses.",
                evidence=f"Origin: {_EVIL_ORIGIN} -> Access-Control-Allow-Origin: {allow_origin}"
                + (", Access-Control-Allow-Credentials: true" if allows_credentials else ""),
                recommendation="Reflect only an allow-list of trusted origins; never combine a wildcard origin with "
                "credentials.",
                cwe_id="CWE-942",
                owasp_category="A05:2021 Security Misconfiguration",
                vulnerability_type="cors_misconfiguration",
            )
        ]


def _is_success(status: int) -> bool:
    return 200 <= status < 300


#: How many rapid requests the rate-limit check sends before concluding none were throttled.
_RATE_BURST = 8

# (probe value, detector method, how to build the mutated parameter value). Kept as a table so
# scan_endpoint runs one request per probe with no branching.
_PARAM_PROBES: List[
    Tuple[str, Callable[["ActiveAPIScanner", str, str, Response], Optional[DASTFinding]], Callable[[str], str]]
] = [
    (_SQLI_PROBE, ActiveAPIScanner._detect_sqli, lambda original: original + _SQLI_PROBE),
    (_XSS_PROBE, ActiveAPIScanner._detect_xss, lambda _original: _XSS_PROBE),
    (_TRAVERSAL_PROBE, ActiveAPIScanner._detect_traversal, lambda _original: _TRAVERSAL_PROBE),
]


@dataclass
class ActiveScanConfig:
    """How the active scanner is turned on and bounded. Threaded from the CLI through
    ``APISecurityTester`` / ``DASTAnalyzer`` so the gate lives in one place."""

    active: bool = False
    authorized: bool = False
    rate_limit_rps: float = 5.0
    transport: Optional[Transport] = field(default=None, repr=False)
