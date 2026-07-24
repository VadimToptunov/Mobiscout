"""Parse a HAR (HTTP Archive) capture into ``APICall`` objects.

A HAR file is what a proxy (mitmproxy, Charles, Chrome DevTools, the framework's
own ``mock`` proxy) exports for recorded HTTP traffic. This turns its
``log.entries`` into the ``APICall`` shape the API analyzer consumes, so a real
capture can be analysed for patterns and turned into test assertions.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.api_analyzer.api_log_analyzer import APICall, APIMethod


def _headers(entries: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
    """HAR headers are ``[{"name": ..., "value": ...}]`` -> a flat dict."""
    return {h.get("name", ""): h.get("value", "") for h in (entries or []) if h.get("name")}


def _parse_ts(value: Optional[str]) -> datetime:
    """Parse a HAR ISO-8601 ``startedDateTime`` (``Z`` allowed); epoch on failure
    so the result stays deterministic rather than falling back to 'now'."""
    if not value:
        return datetime.fromtimestamp(0)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.fromtimestamp(0)


def load_har_calls(path: Path) -> List[APICall]:
    """Load the API calls from a HAR file.

    Entries whose HTTP method is not one Mobiscout models (``APIMethod``) are
    skipped rather than aborting the whole parse.

    Args:
        path: the ``.har`` file to read.

    Returns:
        The parsed API calls, in file order.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    calls: List[APICall] = []
    for entry in data.get("log", {}).get("entries", []):
        request = entry.get("request", {}) or {}
        response = entry.get("response", {}) or {}
        try:
            method = APIMethod((request.get("method") or "GET").upper())
        except ValueError:
            continue  # a method we don't model (e.g. TRACE) — skip it
        calls.append(
            APICall(
                timestamp=_parse_ts(entry.get("startedDateTime")),
                method=method,
                url=request.get("url", ""),
                request_headers=_headers(request.get("headers")),
                request_body=(request.get("postData") or {}).get("text"),
                response_status=response.get("status"),
                response_headers=_headers(response.get("headers")),
                response_body=(response.get("content") or {}).get("text"),
                duration_ms=entry.get("time"),
            )
        )
    return calls
