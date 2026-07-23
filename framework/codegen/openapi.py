"""
OpenAPI / Swagger ingestion + review.

A backend's OpenAPI (a.k.a. Swagger) spec is a ready-made contract: every
endpoint, its request/response schema, and its auth. Feeding it in gives the
generators real context they otherwise have to guess from captured traffic:

    spec --> parse_openapi --> [APICall]  --> emit_api_tests --> API tests
         --> review_openapi --> [ReviewFinding] + inventory (test-writing context)

Supports OpenAPI 3.x (``requestBody``/``components``) and Swagger 2.0
(``parameters`` with ``in: body`` / ``definitions``); ``$ref`` is resolved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast, Any, Dict, List, Optional

from framework.model.api import APICall

_HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options")
_BODY_METHODS = ("post", "put", "patch")


def load_spec(source: str) -> Dict[str, Any]:
    """Load an OpenAPI/Swagger document from a local path OR an http(s) URL.

    Specs are commonly served live (``/openapi.json``, ``/v3/api-docs``), so a URL
    is accepted directly. Format is taken from the ``.yaml``/``.yml`` suffix, else
    auto-detected (try JSON, fall back to YAML) since URLs often omit an extension.
    """
    if source.startswith(("http://", "https://")):
        import urllib.request

        with urllib.request.urlopen(source, timeout=30) as resp:  # nosec B310 - explicit http(s) scheme
            text = resp.read().decode("utf-8")
    else:
        text = Path(source).read_text(encoding="utf-8")

    if source.endswith((".yaml", ".yml")):
        import yaml

        return cast(Dict[str, Any], yaml.safe_load(text))
    try:
        return cast(Dict[str, Any], json.loads(text))
    except json.JSONDecodeError:
        import yaml

        return cast(Dict[str, Any], yaml.safe_load(text))


def _resolve_ref(spec: Dict[str, Any], node: Any, _seen: Optional[set] = None) -> Any:
    """Follow a local ``$ref`` (e.g. ``#/components/schemas/Pet``) one level."""
    if not isinstance(node, dict) or "$ref" not in node:
        return node
    ref = node["$ref"]
    _seen = _seen or set()
    if ref in _seen or not ref.startswith("#/"):
        return {}
    _seen.add(ref)
    target: Any = spec
    for part in ref[2:].split("/"):
        if not isinstance(target, dict) or part not in target:
            return {}
        target = target[part]
    return _resolve_ref(spec, target, _seen)


def _schema_fields(spec: Dict[str, Any], schema: Any) -> Dict[str, str]:
    """Flatten an object schema to ``{property: type}`` (one level, refs resolved)."""
    schema = _resolve_ref(spec, schema)
    if not isinstance(schema, dict):
        return {}
    props = _resolve_ref(spec, schema.get("properties", {}))
    fields: Dict[str, str] = {}
    if isinstance(props, dict):
        for name, prop in props.items():
            prop = _resolve_ref(spec, prop)
            fields[name] = prop.get("type", "object") if isinstance(prop, dict) else "object"
    return fields


def _request_schema(spec: Dict[str, Any], op: Dict[str, Any]) -> Dict[str, str]:
    """Extract the request body's fields (OpenAPI 3 requestBody or Swagger 2 body param)."""
    body = op.get("requestBody")  # OpenAPI 3.x
    if isinstance(body, dict):
        content = _resolve_ref(spec, body).get("content", {})
        for media, media_obj in content.items():
            if "json" in media and isinstance(media_obj, dict):
                return _schema_fields(spec, media_obj.get("schema", {}))
    for param in op.get("parameters", []):  # Swagger 2.0 body param
        param = _resolve_ref(spec, param)
        if isinstance(param, dict) and param.get("in") == "body":
            return _schema_fields(spec, param.get("schema", {}))
    return {}


def parse_openapi(spec: Dict[str, Any]) -> List[APICall]:
    """Turn an OpenAPI/Swagger spec into APICall objects (one per operation)."""
    calls: List[APICall] = []
    used: set = set()
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            name = op.get("operationId") or f"{method.lower()}_{path.strip('/').replace('/', '_') or 'root'}"
            base = name
            i = 2
            while name in used:
                name = f"{base}_{i}"
                i += 1
            used.add(name)
            responses = [{"status": code} for code in (op.get("responses") or {}).keys()]
            calls.append(
                APICall(  # type: ignore[call-arg]  # triggers_state_change is optional (default None)
                    name=name,
                    endpoint=path,
                    method=method.upper(),
                    request_schema=_request_schema(spec, op) if method.lower() in _BODY_METHODS else {},
                    responses=responses,
                )
            )
    return calls


@dataclass
class ReviewFinding:
    severity: str  # high | medium | low | info
    endpoint: str  # "POST /pets"
    issue: str
    recommendation: str


def review_openapi(spec: Dict[str, Any]) -> List[ReviewFinding]:
    """Lint the spec for gaps that weaken generated tests / hurt testability."""
    findings: List[ReviewFinding] = []
    global_security = bool(spec.get("security"))
    has_security_schemes = bool(
        (spec.get("components", {}) or {}).get("securitySchemes") or spec.get("securityDefinitions")
    )
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        declared_params = {
            p.get("name") for p in item.get("parameters", []) if isinstance(p, dict) and p.get("in") == "path"
        }
        for method, op in item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            where = f"{method.upper()} {path}"
            if not op.get("operationId"):
                findings.append(
                    ReviewFinding("low", where, "No operationId", "Add operationId for stable, readable test names.")
                )
            responses = op.get("responses") or {}
            if not responses:
                findings.append(
                    ReviewFinding("medium", where, "No responses documented", "Declare at least one response code.")
                )
            elif not any(str(c).startswith("2") for c in responses):
                findings.append(
                    ReviewFinding("low", where, "No 2xx success response", "Document the success response.")
                )
            if method.lower() in _BODY_METHODS and not _request_schema(spec, op):
                findings.append(
                    ReviewFinding(
                        "medium",
                        where,
                        "Write operation has no request body schema",
                        "Define requestBody schema so tests can build a valid payload.",
                    )
                )
            op_params = {
                p.get("name") for p in op.get("parameters", []) if isinstance(p, dict) and p.get("in") == "path"
            }
            for token in _path_params(path):
                if token not in declared_params | op_params:
                    findings.append(
                        ReviewFinding(
                            "medium",
                            where,
                            f"Path parameter '{token}' not declared",
                            "Declare the path parameter so its type/format is known.",
                        )
                    )
            if op.get("deprecated"):
                findings.append(
                    ReviewFinding("info", where, "Operation is deprecated", "Skip or flag deprecated endpoints.")
                )
            if not global_security and not op.get("security") and has_security_schemes:
                findings.append(
                    ReviewFinding(
                        "low", where, "No auth applied though schemes exist", "Apply a securityScheme or mark public."
                    )
                )
    return findings


def _path_params(path: str) -> List[str]:
    return [seg[1:-1] for seg in path.split("/") if seg.startswith("{") and seg.endswith("}")]


def review_markdown(spec: Dict[str, Any], calls: List[APICall], findings: List[ReviewFinding]) -> str:
    """A test-writer's API context sheet: endpoint inventory + spec review."""
    info = spec.get("info", {}) or {}
    title = info.get("title", "API")
    version = info.get("version", "")
    out: List[str] = [f"# API context — {title} {version}".rstrip(), ""]
    out.append(f"{len(calls)} operation(s) across {len(spec.get('paths') or {})} path(s).\n")

    out.append("## Endpoints")
    out.append("| Method | Path | Operation | Body fields | Responses |")
    out.append("|---|---|---|---|---|")
    for c in calls:
        body = ", ".join(c.request_schema.keys()) or "—"
        codes = ", ".join(str(r.get("status")) for r in c.responses) or "—"
        out.append(f"| {c.method} | `{c.endpoint}` | {c.name} | {body} | {codes} |")
    out.append("")

    out.append("## Review")
    if findings:
        order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        out.append(f"{len(findings)} finding(s):\n")
        for f in sorted(findings, key=lambda x: order.get(x.severity, 9)):
            out.append(f"- **{f.severity.upper()}** · `{f.endpoint}` — {f.issue}. {f.recommendation}")
    else:
        out.append("No issues found — the spec is well-formed for test generation.")
    out.append("")
    return "\n".join(out)
