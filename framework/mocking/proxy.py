"""
Recording / replay HTTP proxy for API mocking.

This is the server that was missing behind ``mobiscout mock record`` / ``mobiscout
mock replay``: a forward HTTP proxy the app under test points at
(``http://<host>:<port>``), wired into an :class:`~framework.mocking.APIMocker`
session.

Two modes, driven by the mocker's active session:

* **record** — every request is forwarded to its real destination; the
  round-trip (request + response + latency) is captured into the session, and the
  real response is returned to the app untouched.
* **replay** — a request is answered from the recorded mocks (URL/method, plus
  body in strict mode) with no network call; a miss returns ``504`` so the gap is
  visible instead of silently hitting the backend.

HTTPS (``CONNECT``) is passed through as a blind tunnel so the app keeps working,
but its encrypted bodies are **not** recorded — that needs TLS interception with a
trusted CA, which is deliberately out of scope here. The proxy counts and reports
how many HTTPS tunnels it passed through so the limitation is never silent.

    with MockProxy(mocker, port=8888) as proxy:   # background thread (tests)
        ...
    MockProxy(mocker, port=8888).serve_forever()   # blocking (CLI)
"""

from __future__ import annotations

import logging
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Hop-by-hop headers (RFC 7230 §6.1) plus proxy-specific ones: these describe a
# single transport hop and must not be forwarded verbatim through a proxy.
_HOP_BY_HOP = frozenset(
    h.lower()
    for h in (
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "content-length",
    )
)


def _strip_hop_by_hop(headers: dict) -> dict:
    """Return a copy of ``headers`` without hop-by-hop / length fields."""
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}


class _ProxyHandler(BaseHTTPRequestHandler):
    """Handles one proxied request; the owning :class:`MockProxy` is on the server.

    A forward-proxy request carries the absolute target URL in the request line
    (``GET http://host/path HTTP/1.1``), which is exactly what ``self.path`` holds,
    so no separate upstream address is needed.
    """

    protocol_version = "HTTP/1.1"

    # BaseHTTPRequestHandler logs every request to stderr; route it through logging.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature is fixed
        logger.debug("proxy %s - %s", self.address_string(), format % args)

    @property
    def _proxy(self) -> "MockProxy":
        return self.server.mock_proxy  # type: ignore[attr-defined,no-any-return]

    def _read_body(self) -> Optional[str]:
        """Read the request body per ``Content-Length``; ``None`` if there is none."""
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return None
        return self.rfile.read(length).decode("utf-8", errors="replace")

    def _write(self, status: int, headers: dict, body: str) -> None:
        """Write a full response (status line, headers, framed body) to the client."""
        payload = body.encode("utf-8", errors="replace")
        self.send_response(status)
        for key, value in _strip_hop_by_hop(headers).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self) -> None:
        """Dispatch one HTTP request through the active record/replay session."""
        method = self.command
        url = self.path
        body = self._read_body()
        req_headers = _strip_hop_by_hop(dict(self.headers))
        mocker = self._proxy.mocker

        session = mocker.active_session
        if session is None:  # nothing to do without a session — pass through opaquely
            self._write(502, {"Content-Type": "text/plain"}, "No active mock session")
            return

        if session.mode.value == "replay":
            self._serve_from_mock(method, url, req_headers, body)
        else:
            self._record_and_forward(method, url, req_headers, body)

    def _serve_from_mock(self, method: str, url: str, headers: dict, body: Optional[str]) -> None:
        """Replay: answer from a recorded mock, or ``504`` on a miss."""
        mocked = self._proxy.mocker.intercept_request(method, url, headers, body)
        if mocked is not None:
            self._write(mocked["status_code"], mocked["headers"], mocked["body"])
            return
        self._write(
            504,
            {"Content-Type": "application/json"},
            '{"error": "no recorded mock for this request", "method": "%s", "url": "%s"}' % (method, url),
        )

    def _record_and_forward(self, method: str, url: str, headers: dict, body: Optional[str]) -> None:
        """Record: forward to the real destination, capture the round-trip, return it."""
        try:
            started = time.monotonic()
            upstream = requests.request(
                method,
                url,
                headers=headers,
                data=body.encode("utf-8") if body is not None else None,
                allow_redirects=False,
                timeout=self._proxy.upstream_timeout,
            )
            latency_ms = (time.monotonic() - started) * 1000.0
        except requests.RequestException as exc:
            logger.warning("upstream request failed: %s %s -> %s", method, url, exc)
            self._write(502, {"Content-Type": "text/plain"}, f"Upstream request failed: {exc}")
            return

        resp_headers = dict(upstream.headers)
        resp_body = upstream.text
        self._proxy.mocker.record_response(
            method=method,
            url=url,
            request_headers=headers,
            request_body=body,
            response_status=upstream.status_code,
            response_headers=resp_headers,
            response_body=resp_body,
            latency_ms=latency_ms,
        )
        self._write(upstream.status_code, resp_headers, resp_body)

    # Every HTTP verb funnels through _handle.
    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _handle

    def do_CONNECT(self) -> None:
        """Blind-tunnel an HTTPS ``CONNECT`` (no recording; count it and pass through).

        HTTPS bodies can't be recorded without terminating TLS with a trusted CA,
        which this proxy intentionally doesn't do — so the encrypted bytes are
        relayed verbatim between the app and the real host, and the tunnel is
        counted so callers can see how much traffic went un-recorded.
        """
        self._proxy.note_https_tunnel()
        host, _, port = self.path.partition(":")
        try:
            upstream = socket.create_connection((host, int(port or 443)), timeout=self._proxy.upstream_timeout)
        except OSError as exc:
            self._write(502, {"Content-Type": "text/plain"}, f"CONNECT failed: {exc}")
            return

        self.send_response(200, "Connection Established")
        self.end_headers()
        self._relay(self.connection, upstream)

    @staticmethod
    def _relay(client: socket.socket, upstream: socket.socket) -> None:
        """Pump bytes both ways between client and upstream until either closes."""
        sockets = [client, upstream]
        try:
            while True:
                readable, _, errored = select.select(sockets, [], sockets, 60)
                if errored or not readable:
                    break
                for src in readable:
                    data = src.recv(65536)
                    if not data:
                        return
                    (upstream if src is client else client).sendall(data)
        finally:
            upstream.close()


class MockProxy:
    """A record/replay HTTP proxy bound to an :class:`APIMocker`'s active session.

    Args:
        mocker: an APIMocker with an active recording or replay session
            (``start_recording`` / ``start_replay`` must have been called).
        port: TCP port to listen on; ``0`` picks an ephemeral port (useful in tests,
            read back via :attr:`address`).
        host: bind address; defaults to loopback.
        upstream_timeout: seconds to wait on the real backend when recording.
    """

    def __init__(self, mocker: Any, port: int = 8888, host: str = "127.0.0.1", upstream_timeout: float = 30.0) -> None:
        self.mocker = mocker
        self.upstream_timeout = upstream_timeout
        self._server = ThreadingHTTPServer((host, port), _ProxyHandler)
        self._server.mock_proxy = self  # type: ignore[attr-defined]
        self._thread: Optional[threading.Thread] = None
        self._https_tunnels = 0
        self._lock = threading.Lock()

    @property
    def address(self) -> Tuple[str, int]:
        """The bound ``(host, port)`` — reflects the real port when ``0`` was given."""
        return self._server.server_address  # type: ignore[return-value]

    @property
    def https_tunnels(self) -> int:
        """How many HTTPS ``CONNECT`` tunnels were passed through un-recorded."""
        return self._https_tunnels

    def note_https_tunnel(self) -> None:
        """Record that one HTTPS tunnel was passed through (thread-safe)."""
        with self._lock:
            self._https_tunnels += 1

    def serve_forever(self) -> None:
        """Serve in the foreground until interrupted (the CLI entry point)."""
        self._server.serve_forever()

    def start(self) -> "MockProxy":
        """Start serving on a background daemon thread and return self."""
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop the server and join its thread."""
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self) -> "MockProxy":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()
