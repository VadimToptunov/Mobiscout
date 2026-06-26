"""
Security Scanning CLI Commands

Commands for automated security testing.

This module has been refactored into a modular structure.
See framework/cli/security/ for individual command modules:
- base.py: Shared utilities and CLI group
- basic.py: Basic commands (scan, audit, list, compare)
- advanced.py: Advanced commands (secrets, pinning, binary, privacy, rootcheck, code, full, owasp)
- sast.py: SAST commands (sast, taint)
- dast.py: DAST commands (dast, ssl, api)
- decompiler_cmd.py: Decompiler commands (decompile, strings)
- supply_chain_cmd.py: Supply chain commands (supply-chain, sbom)
- runtime_cmd.py: Runtime protection commands (runtime, protections)
- comprehensive_cmd.py: Comprehensive analysis command

STEP 9: Advanced Security Testing CLI
"""

# Re-export the security CLI group with all commands attached
from framework.cli.security import security

__all__ = ["security"]
