"""
Security CLI Commands Package

Modular security scanning commands organized by functionality:
- base: Shared utilities and CLI group
- basic: Basic security scan commands (scan, audit, list, compare)
- sast: Static Application Security Testing commands
- dast: Dynamic Application Security Testing commands
- decompiler: Decompilation and reverse engineering commands
- supply_chain: Supply chain security commands
- runtime: Runtime protection analysis commands
- comprehensive: Full comprehensive analysis command
"""

from framework.cli.security.base import security
from framework.cli.security.basic import scan, audit, list_checks, compare
from framework.cli.security.advanced import secrets, pinning, binary, privacy, rootcheck, code, full, owasp
from framework.cli.security.sast import sast, taint
from framework.cli.security.dast import dast, ssl, api
from framework.cli.security.decompiler_cmd import decompile, strings
from framework.cli.security.supply_chain_cmd import supply_chain, sbom
from framework.cli.security.runtime_cmd import runtime, protections
from framework.cli.security.comprehensive_cmd import comprehensive

__all__ = [
    "security",
    # Basic commands
    "scan",
    "audit",
    "list_checks",
    "compare",
    # Advanced commands
    "secrets",
    "pinning",
    "binary",
    "privacy",
    "rootcheck",
    "code",
    "full",
    "owasp",
    # SAST commands
    "sast",
    "taint",
    # DAST commands
    "dast",
    "ssl",
    "api",
    # Decompiler commands
    "decompile",
    "strings",
    # Supply chain commands
    "supply_chain",
    "sbom",
    # Runtime commands
    "runtime",
    "protections",
    # Comprehensive
    "comprehensive",
]
