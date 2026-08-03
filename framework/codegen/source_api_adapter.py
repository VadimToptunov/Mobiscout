"""Adapt statically-extracted API endpoints into codegen ``APICall`` inputs.

Bridges the source analyzers — which discover the endpoints an app actually calls
(Retrofit interfaces on Android via ``AnalysisResult.api_endpoints``, URLSession
contracts on iOS via ``APIContract``) — to the codegen model, so
``generate api-tests --source <dir>`` produces API tests from the app's *own
code*, not only from a user-supplied OpenAPI spec.

Source gives an endpoint's method/path (and a request/response *type name*), but
no response schema or status codes, so the resulting ``APICall`` carries empty
schemas — the generated test still exercises the endpoint. When the analyzer does
infer schemas (the business-analyzer ``APIContract`` path), they are carried
through.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Set
from urllib.parse import urlparse

from framework.model.api import APICall


def _slug(path: str) -> str:
    """A short, name-safe slug for a URL path (used to derive a call name)."""
    cleaned = "".join(char if char.isalnum() else "_" for char in path).strip("_")
    return (cleaned or "root").lower()[:40]


def _as_path(endpoint: str) -> str:
    """Reduce a full URL to its path so the generated test can prepend BASE_URL.
    iOS URLSession calls carry absolute URLs; Android Retrofit paths pass through."""
    if endpoint.startswith(("http://", "https://")):
        return urlparse(endpoint).path or "/"
    return endpoint


def _unique(name: str, seen: Set[str]) -> str:
    """A collision-free name (endpoints keyed by name in the codegen model, so two
    same-named calls would otherwise clobber each other)."""
    candidate = name
    index = 2
    while candidate in seen:
        candidate = f"{name}_{index}"
        index += 1
    seen.add(candidate)
    return candidate


def endpoints_to_api_calls(endpoints: Iterable[Any]) -> List[APICall]:
    """Map Android ``AnalysisResult.api_endpoints`` (``APIEndpointCandidate``:
    method / path / function_name / request_type / response_type) to ``APICall``.
    Schemas stay empty — source exposes only type names, not shapes."""
    calls: List[APICall] = []
    seen: Set[str] = set()
    for endpoint in endpoints:
        method = (getattr(endpoint, "method", "") or "GET").upper()
        path = getattr(endpoint, "path", "") or ""
        function_name = getattr(endpoint, "function_name", "") or ""
        name = _unique(function_name or f"{method.lower()}_{_slug(path)}", seen)
        # triggers_state_change is optional (default None); mypy can't see the
        # pydantic Field default without the plugin, as in codegen/openapi.py.
        calls.append(APICall(name=name, endpoint=path, method=method))  # type: ignore[call-arg]
    return calls


def contracts_to_api_calls(contracts: Iterable[Any]) -> List[APICall]:
    """Map ``APIContract`` (the business-analyzer / iOS path) to ``APICall`` —
    richer: it carries the request/response schemas the analyzer inferred."""
    calls: List[APICall] = []
    seen: Set[str] = set()
    for contract in contracts:
        method = (getattr(contract, "method", "") or "GET").upper()
        endpoint = _as_path(getattr(contract, "endpoint", "") or "")
        name = _unique(f"{method.lower()}_{_slug(endpoint)}", seen)
        responses: List[Dict[str, Any]] = []
        response_schema = getattr(contract, "response_schema", None)
        if response_schema:
            responses.append({"status": 200, "schema": response_schema})
        responses.extend(getattr(contract, "error_responses", None) or [])
        calls.append(
            APICall(  # type: ignore[call-arg]  # triggers_state_change is optional (default None)
                name=name,
                endpoint=endpoint,
                method=method,
                request_schema=dict(getattr(contract, "request_schema", None) or {}),
                responses=responses,
            )
        )
    return calls


def har_calls_to_api_calls(har_calls: Iterable[Any]) -> List[APICall]:
    """Convert captured HAR traffic (``api_analyzer.APICall``) to ``model.APICall``.

    Repeated calls to the same ``(method, path)`` are grouped and their **observed**
    response statuses unioned, so the generated test asserts the status the API
    actually returned (the strengthened assertion in ``api_test``). Absolute URLs
    are reduced to paths (the test prepends BASE_URL)."""
    grouped: Dict[tuple, Set[int]] = {}
    order: List[tuple] = []
    for call in har_calls:
        raw_method = getattr(call, "method", None)
        method = str(getattr(raw_method, "value", raw_method) or "GET").upper()
        path = _as_path(getattr(call, "url", "") or "")
        key = (method, path)
        if key not in grouped:
            grouped[key] = set()
            order.append(key)
        status = getattr(call, "response_status", None)
        if status:
            grouped[key].add(int(status))

    calls: List[APICall] = []
    seen: Set[str] = set()
    for method, path in order:
        name = _unique(f"{method.lower()}_{_slug(path)}", seen)
        responses = [{"status": status} for status in sorted(grouped[(method, path)])]
        # triggers_state_change is optional (default None); see openapi.py.
        calls.append(APICall(name=name, endpoint=path, method=method, responses=responses))  # type: ignore[call-arg]
    return calls


def base_url_from_har(har_calls: Iterable[Any], default: str = "http://localhost:8000") -> str:
    """The backend origin (scheme://host) of the first captured absolute URL, so
    generated tests default to the real backend; ``default`` if none is absolute."""
    for call in har_calls:
        parsed = urlparse(getattr(call, "url", "") or "")
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return default


def _ios_source_api_calls(root: Path) -> List[APICall]:
    """Statically extract the API a Swift/iOS app calls (URLSession) as APICalls."""
    from framework.analyzers.business_logic_analyzer import BusinessLogicAnalysis
    from framework.analyzers.ios_business_analyzer import IOSBusinessAnalyzer

    analysis = BusinessLogicAnalysis(platform="ios")
    IOSBusinessAnalyzer(root, analysis).generate_api_contracts()
    return contracts_to_api_calls(analysis.api_contracts)


def source_api_calls(source_path: str) -> List[APICall]:
    """Statically extract the API an app calls, as ``APICall``s ready for
    ``emit_api_tests``. Auto-detects the platform(s) from the source: Kotlin/Java
    (Android/Retrofit) and/or Swift (iOS/URLSession) — a mixed tree yields both."""
    root = Path(source_path)
    calls: List[APICall] = []

    if any(root.rglob("*.kt")) or any(root.rglob("*.java")):
        from framework.analyzers.android_analyzer import AndroidAnalyzer

        calls.extend(endpoints_to_api_calls(AndroidAnalyzer().analyze(source_path).api_endpoints))

    if any(root.rglob("*.swift")):
        calls.extend(_ios_source_api_calls(root))

    return calls
