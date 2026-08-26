"""A minimal MCP stdio server exposing Mobiscout's engine as tools.

An MCP-capable agent (Claude, etc.) can drive the deterministic engine: enumerate codegen
targets, generate framework tests from an IR (:class:`TestModel`), and crawl a live app
into a full kit. No runtime LLM — the engine is deterministic and offline; MCP is only the
interface.

Transport: newline-delimited JSON-RPC 2.0 over stdio (the MCP stdio transport). There is no
SDK dependency — the handful of methods (``initialize`` / ``tools/list`` / ``tools/call`` /
``ping``) are handled directly, matching the project's zero-runtime-dependency philosophy.

The message dispatcher (:func:`handle_message`) is pure — a dict in, a dict (or None for a
notification) out — so it is fully unit-testable without touching real stdio.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from framework import __version__

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "mobiscout", "version": __version__}

# Reject an over-large line before parsing it — parity with the JSON-RPC daemon's cap, so a
# runaway/hostile client can't push us to json.loads a giant payload.
_MAX_MESSAGE_BYTES = 8 * 1024 * 1024

# Wall-clock backstop for an agent-driven crawl, mirroring the daemon's kit/generate default:
# a wedged device (adb call hanging, dead WDA) would otherwise hold this single-threaded
# server for as long as the crawl takes. A caller-supplied max_seconds still wins.
_DEFAULT_CRAWL_MAX_SECONDS = 600


class ToolError(Exception):
    """A tool-execution failure surfaced to the agent as an ``isError`` result (not a
    protocol error), so the model sees what went wrong and can adjust."""


# --------------------------------------------------------------------------- tools


def _tool_list_targets(_: Dict[str, Any]) -> str:
    """Enumerate the available codegen targets."""
    from framework.codegen import available_targets

    targets = [
        {
            "id": t.id,
            "language": getattr(t.language, "value", str(t.language)),
            "runner": t.runner,
            "description": t.description,
        }
        for t in available_targets()
    ]
    return json.dumps({"targets": targets}, indent=2)


def _tool_generate_tests(args: Dict[str, Any]) -> str:
    """Emit test source for one or more targets from a TestModel IR (device-free)."""
    from framework.codegen import get_emitter
    from framework.codegen.ir import TestModel
    from framework.codegen.targets import _REGISTRY  # noqa: WPS437 — read-only id check

    model_data = args.get("model")
    if not isinstance(model_data, dict):
        raise ToolError("`model` is required and must be a TestModel object (see the IR schema).")
    targets: List[str] = args.get("targets") or ["python_pytest"]
    unknown = [t for t in targets if t not in _REGISTRY]
    if unknown:
        raise ToolError(f"Unknown target(s): {', '.join(unknown)}. Available: {', '.join(sorted(_REGISTRY))}.")
    try:
        model = TestModel.from_dict(model_data)
    except (KeyError, ValueError, TypeError) as e:
        raise ToolError(f"Invalid TestModel: {e}")
    files = {target: get_emitter(target).emit(model) for target in targets}
    return json.dumps({"files": files}, indent=2)


def _tool_crawl_app(args: Dict[str, Any]) -> str:
    """Crawl a live app (device/Appium required) and build the kit; returns the summary."""
    package = args.get("package")
    if not package:
        raise ToolError("`package` (Android package or iOS bundle id) is required.")
    config: Dict[str, Any] = {
        "package": package,
        "platform": args.get("platform", "android"),
        "output": args.get("output", "crawl-kit"),
        "max_seconds": _DEFAULT_CRAWL_MAX_SECONDS,
    }
    for key in (
        "targets",
        "app_activity",
        "serial",
        "udid",
        "device_name",
        "server",
        "max_steps",
        "max_depth",
        "max_seconds",
    ):
        if args.get(key) is not None:
            config[key] = args[key]
    from framework.crawler.pipeline import run_kit

    try:
        summary = run_kit(config)
    except Exception as e:  # a live crawl can fail many ways (no device, Appium down, ...)
        raise ToolError(f"Crawl failed: {e}. Ensure a device/emulator is connected and Appium is reachable.")
    return json.dumps(summary, indent=2, default=str)


# Tool registry: name -> (definition, handler). The definition's inputSchema is a JSON
# Schema the agent uses to shape its arguments.
_TOOL_TABLE: Dict[str, tuple] = {
    "list_targets": (
        {
            "name": "list_targets",
            "description": "List the available Mobiscout codegen targets (id, language, runner, description).",
            "inputSchema": {"type": "object", "properties": {}},
        },
        _tool_list_targets,
    ),
    "generate_tests": (
        {
            "name": "generate_tests",
            "description": (
                "Generate runnable test source from a Mobiscout TestModel IR, for one or more codegen "
                "targets. Device-free and deterministic. Returns {files: {target: {path: content}}}."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "model": {
                        "type": "object",
                        "description": "A TestModel object (the Mobiscout IR): name, app_package, platform, cases[].",
                    },
                    "targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Target ids (e.g. python_pytest, maestro). Defaults to [python_pytest].",
                    },
                },
                "required": ["model"],
            },
        },
        _tool_generate_tests,
    ),
    "crawl_app": (
        {
            "name": "crawl_app",
            "description": (
                "Crawl a running app on a connected device/emulator and build a full test kit "
                "(inventory, interaction graph, coverage, and generated tests). Requires a device and, "
                "for iOS or the appium driver, a reachable Appium server. Returns the kit summary."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "package": {"type": "string", "description": "Android package or iOS bundle id under test."},
                    "platform": {"type": "string", "enum": ["android", "ios"], "description": "Defaults to android."},
                    "targets": {"type": "array", "items": {"type": "string"}, "description": "Codegen target ids."},
                    "output": {"type": "string", "description": "Output directory (default crawl-kit)."},
                    "app_activity": {"type": "string"},
                    "serial": {"type": "string", "description": "adb device serial (Android)."},
                    "udid": {"type": "string", "description": "Device/simulator UDID (Appium)."},
                    "device_name": {"type": "string"},
                    "server": {"type": "string", "description": "Appium server URL."},
                    "max_steps": {"type": "integer"},
                    "max_depth": {"type": "integer"},
                    "max_seconds": {
                        "type": "integer",
                        "description": f"Wall-clock crawl budget (default {_DEFAULT_CRAWL_MAX_SECONDS}).",
                    },
                },
                "required": ["package"],
            },
        },
        _tool_crawl_app,
    ),
}

#: The public tool definitions (as an MCP ``tools/list`` would return them).
TOOLS: List[Dict[str, Any]] = [defn for defn, _ in _TOOL_TABLE.values()]


# --------------------------------------------------------------------------- dispatch


def _result(msg_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """A JSON-RPC 2.0 success response."""
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> Dict[str, Any]:
    """A JSON-RPC 2.0 error response."""
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _call_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a ``tools/call`` to its handler, wrapping the result as MCP content and
    turning a :class:`ToolError` into an ``isError`` result rather than a protocol error."""
    name = params.get("name")
    entry = _TOOL_TABLE.get(name) if isinstance(name, str) else None
    if entry is None:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    _, handler = entry
    try:
        text = handler(params.get("arguments") or {})
    except ToolError as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    except Exception as e:
        # Arguments the schema permits can still break a handler (an IR the emitters
        # choke on, an unreadable path). Report it to the agent instead of letting it
        # unwind through the stdio loop and end the session for every later request.
        return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
    return {"content": [{"type": "text", "text": text}], "isError": False}


def handle_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle one JSON-RPC message. Returns the response dict, or None for a notification
    (a request without an ``id``) which must not be answered."""
    method = msg.get("method")
    msg_id = msg.get("id")
    is_notification = "id" not in msg

    if method is None:  # a response object echoed back to us — ignore
        return None
    if is_notification:  # notifications (e.g. notifications/initialized) get no reply
        return None

    if method == "initialize":
        # Answer with the version we actually implement, never the client's. Echoing e.g.
        # "2025-06-18" would claim semantics this server does not have (structured tool
        # output, elicitation); the spec's rule for an unsupported request is to reply with
        # a version the server does support, and this server supports exactly one.
        return _result(
            msg_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})
    if method == "tools/call":
        return _result(msg_id, _call_tool(msg.get("params") or {}))
    return _error(msg_id, -32601, f"Method not found: {method}")


def serve_stdio(stdin: Any = None, stdout: Any = None) -> None:
    """Run the MCP server over newline-delimited JSON-RPC on stdio until EOF."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        if len(line.encode("utf-8")) > _MAX_MESSAGE_BYTES:
            _write(stdout, _error(None, -32600, "Request too large"))
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _write(stdout, _error(None, -32700, "Parse error"))
            continue
        try:
            response = handle_message(msg)
        except Exception as e:
            # Last resort, mirroring the daemon's _process_line: one malformed message or
            # dispatch bug costs that request, not the whole session.
            msg_id = msg.get("id") if isinstance(msg, dict) else None
            response = _error(msg_id, -32603, f"Internal error: {e}")
        if response is not None:
            _write(stdout, response)


def _write(stdout: Any, obj: Dict[str, Any]) -> None:
    """Write one JSON-RPC message as a single newline-terminated line and flush."""
    stdout.write(json.dumps(obj) + "\n")
    stdout.flush()
