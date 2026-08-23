"""Model Context Protocol (MCP) interface for the Mobiscout engine.

Exposes the deterministic engine (list codegen targets, generate tests from an IR, crawl
a live app into a kit) as MCP tools an agent can call. Mobiscout stays AI-*assisted*, not
AI-*powered*: there is no runtime LLM here — MCP is only the interface an agent talks to.
"""

from framework.mcp.server import TOOLS, handle_message, serve_stdio

__all__ = ["TOOLS", "handle_message", "serve_stdio"]
