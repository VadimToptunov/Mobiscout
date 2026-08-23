"""Generate negative-security API tests from captured traffic (a proxy HAR).

For each captured request this emits, as runnable pytest + requests, the checks a security
reviewer would run by hand:

* **missing-token** — a request that carried an auth header, repeated WITHOUT it, must be
  denied (401/403). Catches an endpoint that forgot to enforce auth.
* **BOLA / IDOR** — a request whose path carries an object id, repeated with a *different*
  id, must not return 200. Catches missing object-level authorization.
* **missing-field** — a POST/PUT/PATCH JSON body with a required field dropped must be
  rejected (4xx). Catches missing input validation.

This is a **test generator, not a live scanner**: it writes files you run against your own
API. Captured credentials are never baked into the output — the auth-required tests send no
token, and the object-authz tests read one from ``MOBISCOUT_API_TOKEN`` (you supply it), so
a generated kit is safe to commit.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

_AUTH_HEADERS = ("authorization", "cookie", "x-api-key", "x-auth-token", "x-access-token")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# The object-authz and missing-field checks are only meaningful with a *valid* token: with
# none, the request is rejected for lack of auth (401) and the assertion passes vacuously —
# a false green. Skip them until MOBISCOUT_API_TOKEN is set, so a pass means the check ran.
_SKIP_WITHOUT_TOKEN = (
    "    if not _AUTH['Authorization']:\n"
    "        pytest.skip('set MOBISCOUT_API_TOKEN to a valid token to run this authenticated check')\n"
)


def _has_auth(headers: Dict[str, str]) -> bool:
    return any(k.lower() in _AUTH_HEADERS for k in (headers or {}))


def _path_of(url: str) -> str:
    return urlparse(url).path or "/"


def _swap_id(path: str) -> Optional[str]:
    """Return the path with an object id swapped for a different value, or None if the path
    has no id-looking segment. Numeric ids are bumped; UUIDs are replaced with a fixed other
    UUID; both changes keep the path shape but point at a *different* object."""
    segments = path.split("/")
    for i, seg in enumerate(segments):
        if seg.isdigit():
            segments[i] = str(int(seg) + 1) if seg != "0" else "999999999"
            return "/".join(segments)
        if _UUID.match(seg):
            segments[i] = "00000000-0000-0000-0000-000000000000"
            return "/".join(segments)
    return None


def _sample_value(value: Any) -> Any:
    """A type-shaped placeholder for a captured body value — so the generated test carries
    the request's *shape*, never its captured contents (which may be a password or token).
    bool is checked before int (``bool`` is a subclass of ``int``)."""
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return 0
    if isinstance(value, float):
        return 0.0
    if isinstance(value, str):
        return "sample"
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    return None


def _drop_a_field(body_text: Optional[str]) -> Optional[Tuple[Dict[str, Any], str]]:
    """Parse a JSON object body and return (body-without-one-key, the-dropped-key), or None
    if the body isn't a non-empty JSON object. The kept fields carry **sample** values, never
    the captured ones, so no secret from the capture is written into the generated test."""
    if not body_text:
        return None
    try:
        data = json.loads(body_text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or not data:
        return None
    dropped = next(iter(data))
    return {k: _sample_value(v) for k, v in data.items() if k != dropped}, dropped


def _slug(text: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    return s or "call"


def emit_api_negative_tests(har_calls: List[Any], base_url: str = "http://localhost:8000") -> Dict[str, str]:
    """Return ``{filename: content}`` for the negative-security API tests, or ``{}`` when
    the capture yields no applicable case."""
    bodies: List[str] = []
    seen: set = set()
    for call in har_calls:
        method = str(getattr(getattr(call, "method", None), "value", getattr(call, "method", "GET"))).upper()
        url = getattr(call, "url", "") or ""
        path = _path_of(url)
        headers = getattr(call, "request_headers", {}) or {}
        body_text = getattr(call, "request_body", None)
        key = (method, path)
        if not path or key in seen:
            continue
        seen.add(key)
        name = f"{method.lower()}_{_slug(path)}"[:60]
        m = method.lower()

        if _has_auth(headers):
            bodies.append(
                f"def test_{name}_requires_auth():\n"
                f'    """Without the auth header the API must deny this request."""\n'
                f"    r = requests.{m}(BASE + {path!r}, timeout=_T)\n"
                f"    assert r.status_code in (401, 403), f'expected auth required, got {{r.status_code}}'\n"
            )
        swapped = _swap_id(path)
        if swapped is not None:
            bodies.append(
                f"def test_{name}_rejects_foreign_object_id():\n"
                f'    """BOLA/IDOR: another object\'s id must not return 200 (object-level authz)."""\n'
                f"{_SKIP_WITHOUT_TOKEN}"
                f"    r = requests.{m}(BASE + {swapped!r}, headers=_AUTH, timeout=_T)\n"
                f"    assert r.status_code != 200, f'foreign id returned 200 (possible BOLA/IDOR)'\n"
            )
        dropped = _drop_a_field(body_text) if m in ("post", "put", "patch") else None
        if dropped is not None:
            partial, field = dropped
            bodies.append(
                f"def test_{name}_rejects_missing_{_slug(field)}():\n"
                f'    """A required field ({field!r}) dropped must be rejected (4xx)."""\n'
                f"{_SKIP_WITHOUT_TOKEN}"
                f"    r = requests.{m}(BASE + {path!r}, json={partial!r}, headers=_AUTH, timeout=_T)\n"
                f"    assert 400 <= r.status_code < 500, f'missing field accepted: {{r.status_code}}'\n"
            )

    if not bodies:
        return {}

    header = (
        '"""Negative-security API tests generated from captured traffic (Mobiscout).\n\n'
        "These run against your own API. Captured credentials are NOT baked in: set\n"
        "MOBISCOUT_API_TOKEN to a valid bearer token for the object-authz / missing-field\n"
        "cases; the auth-required cases deliberately send no token.\n"
        '"""\n\n'
        "import os\n\n"
        "import pytest\n"
        "import requests\n\n"
        f"BASE = os.environ.get('MOBISCOUT_API_BASE', {base_url!r})\n"
        "_AUTH = {'Authorization': os.environ.get('MOBISCOUT_API_TOKEN', '')}\n"
        "_T = 15\n\n\n"
    )
    return {"test_api_security.py": header + "\n\n".join(bodies) + "\n"}
