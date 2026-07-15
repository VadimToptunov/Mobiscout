"""Frozen entry point for the Mobiscout engine daemon (variant C: no user Python).

PyInstaller bundles this + the framework into a standalone per-platform binary the
JetBrains plugin launches; it speaks the same JSON-RPC over stdio as `mobiscout daemon`.
"""
from framework.cli.daemon_commands import JSONRPCServer

if __name__ == "__main__":
    JSONRPCServer().run_stdio()
