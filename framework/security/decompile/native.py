"""Analyzer extracted from decompiler (mechanical split; see decompile/base.py)."""

import re
import subprocess
from pathlib import Path
from typing import Dict, Any


class NativeLibAnalyzer:
    """
    Native Library Analyzer

    Analyzes native libraries (.so, .dylib) for security issues.
    """

    def analyze_so(self, so_path: Path) -> Dict[str, Any]:
        """Analyze ELF shared object"""
        info: Dict[str, Any] = {
            "path": str(so_path),
            "type": "elf",
            "protections": [],
            "imports": [],
            "exports": [],
        }

        try:
            content = so_path.read_bytes()

            # Check ELF magic
            if content[:4] != b"\x7fELF":
                return info

            # Check architecture
            arch_byte = content[4]
            info["arch"] = "32-bit" if arch_byte == 1 else "64-bit" if arch_byte == 2 else "unknown"

            # Check for security features using readelf if available
            try:
                result = subprocess.run(["readelf", "-d", str(so_path)], capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    # Check for RELRO
                    if "BIND_NOW" in result.stdout:
                        info["protections"].append("FULL_RELRO")
                    elif "RELRO" in result.stdout:
                        info["protections"].append("PARTIAL_RELRO")

                    # Check for stack canary
                    if "__stack_chk_fail" in result.stdout:
                        info["protections"].append("STACK_CANARY")

                # Check for PIE
                result = subprocess.run(["readelf", "-h", str(so_path)], capture_output=True, text=True, timeout=30)
                if "DYN" in result.stdout:
                    info["protections"].append("PIE")

            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

            # Extract strings for analysis
            strings = re.findall(rb"[\x20-\x7e]{4,}", content)
            info["string_count"] = len(strings)

        except OSError:
            pass

        return info
