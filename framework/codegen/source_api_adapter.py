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

from typing import Any, Dict, Iterable, List, Set

from framework.model.api import APICall


def _slug(path: str) -> str:
    """A short, name-safe slug for a URL path (used to derive a call name)."""
    cleaned = "".join(char if char.isalnum() else "_" for char in path).strip("_")
    return (cleaned or "root").lower()[:40]


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
        endpoint = getattr(contract, "endpoint", "") or ""
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


def source_api_calls(source_path: str) -> List[APICall]:
    """Statically extract the API an Android app calls (Retrofit) as ``APICall``s,
    ready to hand to ``emit_api_tests``."""
    from framework.analyzers.android_analyzer import AndroidAnalyzer

    result = AndroidAnalyzer().analyze(source_path)
    return endpoints_to_api_calls(result.api_endpoints)
