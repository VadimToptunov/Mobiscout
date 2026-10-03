"""Active API scanning (#314): opt-in, authorized, rate-limited probing.

The headline tests run the real ``urllib`` transport against two local mock servers — one
deliberately vulnerable, one clean — on 127.0.0.1, so "the scanner flags the seeded issues and
raises no false positives" is checked by execution, not by mocking the detectors. The gate and
the rate limiter are unit-tested with an injected transport (no sockets)."""

import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List
from urllib.parse import parse_qs, urlsplit

import pytest

from framework.security.dast.active import (
    ActiveAPIScanner,
    ActiveScanConfig,
    ActiveScanNotAuthorizedError,
    Response,
)
from framework.security.dast.base import DASTSeverity
from framework.security.dast_analyzer import DASTAnalyzer

_VALID_TOKEN = "Bearer validtoken"
_RATE_LIMIT_AFTER = 3  # the clean server starts answering 429 once a path passes this many hits


class _BaseHandler(BaseHTTPRequestHandler):
    hits: Dict[str, int] = {}

    def log_message(self, *_args):  # keep the test output quiet
        pass

    def _params(self) -> Dict[str, str]:
        query = parse_qs(urlsplit(self.path).query)
        return {k: v[0] for k, v in query.items()}

    def _send(self, status: int, body: str, content_type: str = "text/plain", extra: Dict[str, str] = None) -> None:
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    # Both verbs route through the same handler so GET/POST probes land the same way.
    def do_GET(self) -> None:  # noqa: N802 — http.server's required name
        self.route()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.route()

    def _count(self) -> int:
        path = urlsplit(self.path).path
        type(self).hits[path] = type(self).hits.get(path, 0) + 1
        return type(self).hits[path]


class _VulnerableHandler(_BaseHandler):
    """Seeds one issue per path: /item is an injection sink, /me never enforces auth, /data has a
    permissive CORS policy. None of them rate-limit."""

    def route(self) -> None:
        self._count()
        path = urlsplit(self.path).path
        if path == "/item":
            self._item()
        elif path == "/me":
            self._send(200, "account data")  # 200 regardless of Authorization -> auth bypass
        elif path == "/data":
            origin = self.headers.get("Origin", "")
            self._send(
                200,
                "{}",
                "application/json",
                {
                    "Access-Control-Allow-Origin": origin,  # reflects any origin
                    "Access-Control-Allow-Credentials": "true",
                },
            )
        else:
            self._send(404, "not found")

    def _item(self) -> None:
        value = self._params().get("id", "")
        if "'" in value:
            self._send(500, "You have an error in your SQL syntax near ''")
        elif "etc/passwd" in value:
            self._send(200, "root:x:0:0:root:/root:/bin/bash\n")
        elif "<" in value:
            self._send(200, f"<html><body>results for {value}</body></html>", "text/html")  # reflected unescaped
        else:
            self._send(200, "ok")


class _CleanHandler(_BaseHandler):
    """The same surface done right: input escaped, auth enforced, rate limiting after a few
    requests, and CORS that only trusts a fixed origin."""

    def route(self) -> None:
        if self._count() > _RATE_LIMIT_AFTER:
            self._send(429, "slow down", extra=self._cors())
            return
        path = urlsplit(self.path).path
        if path == "/item":
            value = self._params().get("id", "")
            if "etc/passwd" in value:
                self._send(404, "no such item", extra=self._cors())
            else:
                self._send(
                    200, f"<html><body>results for {html.escape(value)}</body></html>", "text/html", self._cors()
                )
        elif path == "/me":
            status = 200 if self.headers.get("Authorization") == _VALID_TOKEN else 401
            self._send(status, "account data" if status == 200 else "unauthorized", extra=self._cors())
        else:
            self._send(404, "not found", extra=self._cors())

    def _cors(self) -> Dict[str, str]:
        # A fixed trusted origin, never the caller's Origin and never "*".
        return {"Access-Control-Allow-Origin": "https://trusted.example"}


def _serve(handler_cls):
    handler_cls.hits = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


@pytest.fixture()
def vulnerable_url():
    server, url = _serve(_VulnerableHandler)
    yield url
    server.shutdown()


@pytest.fixture()
def clean_url():
    server, url = _serve(_CleanHandler)
    yield url
    server.shutdown()


def _scan(base_url, path, method="GET", headers=None, params=None):
    scanner = ActiveAPIScanner(authorized=True, rate_limit_rps=0)  # no pacing in tests
    return scanner.scan_endpoint(f"{base_url}{path}", method, headers, params)


def _types(findings) -> set:
    return {f.vulnerability_type for f in findings}


# --------------------------------------------------------------------------- #
# Against the vulnerable server: the seeded issues are flagged
# --------------------------------------------------------------------------- #
def test_injection_is_flagged(vulnerable_url):
    findings = _scan(vulnerable_url, "/item", params={"id": "1"})
    assert {"sql_injection", "reflected_xss", "path_traversal"} <= _types(findings)
    sqli = next(f for f in findings if f.vulnerability_type == "sql_injection")
    assert sqli.severity is DASTSeverity.CRITICAL and sqli.cwe_id == "CWE-89"


def test_auth_bypass_is_flagged(vulnerable_url):
    findings = _scan(vulnerable_url, "/me", headers={"Authorization": _VALID_TOKEN})
    assert "auth_bypass" in _types(findings)


def test_missing_rate_limit_is_flagged(vulnerable_url):
    findings = _scan(vulnerable_url, "/me", headers={"Authorization": _VALID_TOKEN})
    assert "missing_rate_limit" in _types(findings)


def test_permissive_cors_is_flagged(vulnerable_url):
    findings = _scan(vulnerable_url, "/data")
    cors = next(f for f in findings if f.vulnerability_type == "cors_misconfiguration")
    assert cors.severity is DASTSeverity.HIGH  # reflected origin + credentials


# --------------------------------------------------------------------------- #
# Against the clean server: no false positives
# --------------------------------------------------------------------------- #
def test_clean_injection_endpoint_is_quiet(clean_url):
    assert _scan(clean_url, "/item", params={"id": "1"}) == []


def test_clean_protected_endpoint_is_quiet(clean_url):
    assert _scan(clean_url, "/me", headers={"Authorization": _VALID_TOKEN}) == []


# --------------------------------------------------------------------------- #
# The gate and the rate limiter (no sockets)
# --------------------------------------------------------------------------- #
def test_active_scan_requires_authorization():
    with pytest.raises(ActiveScanNotAuthorizedError):
        ActiveAPIScanner(authorized=False)


def test_disabled_by_default_reports_not_tested():
    # No active config -> passive: one honest INFO finding, no traffic sent.
    result = DASTAnalyzer().test_api("http://example.invalid", endpoints=[{"path": "/x", "method": "GET"}])
    assert [f.severity for f in result.findings] == [DASTSeverity.INFO]
    assert "not performed" in result.findings[0].title.lower()


def test_active_but_unauthorized_config_is_refused():
    with pytest.raises(ActiveScanNotAuthorizedError):
        DASTAnalyzer(ActiveScanConfig(active=True, authorized=False))


def test_rate_limiter_paces_requests():
    calls: List[float] = []
    slept: List[float] = []
    responses = iter([Response(200, "ok", {})] * 10)

    def transport(method, url, headers, data):
        calls.append(0.0)
        return next(responses)

    scanner = ActiveAPIScanner(
        authorized=True,
        rate_limit_rps=4.0,  # -> a 0.25s minimum interval between requests
        transport=transport,
        sleep=slept.append,
    )
    scanner._request("GET", "http://x")
    scanner._request("GET", "http://x")
    scanner._request("GET", "http://x")
    # The first request doesn't wait; each subsequent one is asked to sleep up to the interval.
    assert len(calls) == 3
    assert len(slept) >= 1 and all(0 < s <= 0.25 for s in slept)
