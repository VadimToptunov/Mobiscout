"""``mobiscout mcp`` — run the Model Context Protocol server over stdio.

Register this with an MCP-capable client (Claude Desktop/Code, etc.) so an agent can drive
the engine as tools. Example client config entry:

    {"command": "mobiscout", "args": ["mcp"]}

The engine stays deterministic and offline — no runtime LLM; MCP is only the interface.
"""

from __future__ import annotations

import click


@click.command("mcp")
def mcp() -> None:
    """Serve the Mobiscout engine over the Model Context Protocol (stdio)."""
    from framework.mcp.server import serve_stdio

    serve_stdio()
