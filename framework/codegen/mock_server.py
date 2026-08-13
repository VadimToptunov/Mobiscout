"""
Mock layer — turn captured traffic into a deterministic backend.

A crawl of an app with a flaky or rate-limited backend produces flaky data and
flaky generated tests (see the crawl-robustness notes). The same proxy HAR that
seeds the API contract tests also carries every response the app received — so we
can replay them: emit a tiny self-contained replay server plus a ``recordings``
file, and point the app or the generated tests at it. Now every run sees the same
responses, no live backend required.

Pure and device-free: :func:`build_recordings` is a straight transform of the
captured calls, and the emitted server is stdlib-only (no dependencies to install
in the kit).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List
from urllib.parse import urlsplit

# The replay server, emitted verbatim into the kit. Stdlib only. ``{port}`` is the
# one substitution (the default port, taken from the kit's base URL).
_SERVER_TEMPLATE = '''#!/usr/bin/env python3
"""Deterministic replay server for the API traffic captured during the crawl.

Serves the recorded responses so tests run against a stable backend instead of a
flaky or live one. Point your app / the generated tests' base URL at this.

    python mock_server.py [--port {port}] [--recordings recordings.json]
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

_RECORDINGS = {{}}


def _load(path):
    for rec in json.loads(Path(path).read_text(encoding="utf-8")):
        _RECORDINGS[(rec["method"].upper(), rec["path"])] = rec


class Handler(BaseHTTPRequestHandler):
    def _serve(self):
        path = urlsplit(self.path).path or "/"
        rec = _RECORDINGS.get((self.command, path))
        if rec is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{{"error": "no recording for this request"}}')
            return
        body = (rec.get("body") or "").encode("utf-8")
        self.send_response(int(rec.get("status") or 200))
        for key, value in (rec.get("headers") or {{}}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _serve

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default={port})
    parser.add_argument("--recordings", default=str(Path(__file__).parent / "recordings.json"))
    args = parser.parse_args()
    _load(args.recordings)
    print(f"mobiscout mock: {{len(_RECORDINGS)}} recordings on http://127.0.0.1:{{args.port}}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
'''


def _method(call: Any) -> str:
    method = getattr(call, "method", "GET")
    return (method.value if hasattr(method, "value") else str(method)).upper()


def build_recordings(api_calls: Iterable[Any]) -> List[Dict[str, Any]]:
    """One recording per (method, path), keyed off the captured calls. Prefers the
    first non-5xx response for a route so replay is deterministic and doesn't
    reproduce the flaky backend's own errors — the whole point of the mock."""
    best: Dict[tuple, Dict[str, Any]] = {}
    for call in api_calls:
        url = getattr(call, "url", "") or ""
        path = urlsplit(url).path or "/"
        method = _method(call)
        key = (method, path)
        status = int(getattr(call, "response_status", None) or 200)
        headers = getattr(call, "response_headers", None) or {}
        content_type = headers.get("Content-Type") or headers.get("content-type") or "application/json"
        record = {
            "method": method,
            "path": path,
            "status": status,
            "headers": {"Content-Type": content_type},
            "body": getattr(call, "response_body", None) or "",
        }
        if key not in best or (best[key]["status"] >= 500 and status < 500):
            best[key] = record
    return list(best.values())


def _readme(base_url: str, count: int) -> str:
    return (
        "# Mock backend (recorded traffic)\n\n"
        f"{count} responses captured during the crawl, replayed deterministically so "
        "tests don't depend on a live/flaky backend.\n\n"
        "```bash\npython mock_server.py --port {port}\n```\n\n"
        f"Then run the tests with their base URL pointed at `{base_url}` "
        "(matching is by HTTP method + path).\n"
    ).replace("{port}", str(urlsplit(base_url).port or 8000))


def emit_mock_server(api_calls: Iterable[Any], base_url: str = "http://localhost:8000") -> Dict[str, str]:
    """The mock-layer files for the kit: ``recordings.json`` (the captured
    responses), ``mock_server.py`` (a stdlib replay server), and a README. Empty
    when there's nothing recorded."""
    recordings = build_recordings(api_calls)
    if not recordings:
        return {}
    port = urlsplit(base_url).port or 8000
    return {
        "recordings.json": json.dumps(recordings, indent=2, ensure_ascii=False) + "\n",
        "mock_server.py": _SERVER_TEMPLATE.format(port=port),
        "README.md": _readme(base_url, len(recordings)),
    }
