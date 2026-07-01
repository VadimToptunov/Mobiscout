"""Analyzer extracted from advanced_security (mechanical split; see advanced/base.py)."""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Pattern, Set, Tuple, Union
from urllib.parse import parse_qs, urlparse

from framework.security.advanced.base import (
    OWASPMobileTop10,
    RiskLevel,
    SecurityVulnerability,
    SecretPattern,
)

logger = logging.getLogger(__name__)


class BinarySecurityAnalyzer:
    """
    Analyzes compiled binaries for security issues

    Checks for:
    - Stack canaries
    - PIE (Position Independent Executable)
    - RELRO (Relocation Read-Only)
    - NX bit (Non-Executable stack)
    - Stripped binaries
    - Debugging symbols
    """

    def analyze_android_apk(self, apk_path: Path) -> List[SecurityVulnerability]:
        """Analyze Android APK for binary security issues"""
        vulnerabilities = []

        # Per-run private temp dir: a shared, world-writable /tmp/apk_analysis
        # invited symlink attacks and let concurrent scans clobber each other.
        out_dir = tempfile.mkdtemp(prefix="apk_analysis_")

        try:
            # Check if apktool is available
            result = subprocess.run(
                ["apktool", "d", str(apk_path), "-o", out_dir, "-f"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.warning(f"apktool failed: {result.stderr}")
                return vulnerabilities

            # Check AndroidManifest.xml
            manifest_path = Path(out_dir) / "AndroidManifest.xml"
            if manifest_path.exists():
                manifest = manifest_path.read_text()

                # Check for debuggable flag
                if 'android:debuggable="true"' in manifest:
                    vulnerabilities.append(
                        SecurityVulnerability(
                            id="BIN-DEBUGGABLE",
                            title="Application is Debuggable",
                            description="The android:debuggable flag is set to true, allowing "
                            "attackers to attach a debugger to the application.",
                            owasp_category=OWASPMobileTop10.M7_INSUFFICIENT_BINARY_PROTECTION,
                            risk_level=RiskLevel.HIGH,
                            cvss_score=7.5,
                            cwe_ids=[489],  # CWE-489: Active Debug Code
                            location="AndroidManifest.xml",
                            evidence='android:debuggable="true"',
                            remediation="Set android:debuggable to false in release builds.",
                            references=[],
                        )
                    )

                # Check for backup flag
                if 'android:allowBackup="true"' in manifest:
                    vulnerabilities.append(
                        SecurityVulnerability(
                            id="BIN-BACKUP",
                            title="Application Backup Allowed",
                            description="android:allowBackup is true, allowing backup of app data "
                            "which may contain sensitive information.",
                            owasp_category=OWASPMobileTop10.M9_INSECURE_DATA_STORAGE,
                            risk_level=RiskLevel.MEDIUM,
                            cvss_score=5.0,
                            cwe_ids=[530],  # CWE-530: Exposure of Backup File
                            location="AndroidManifest.xml",
                            evidence='android:allowBackup="true"',
                            remediation="Set android:allowBackup to false or implement BackupAgent.",
                            references=[],
                        )
                    )

                # Check for exported components
                exported_pattern = re.compile(r'android:exported="true"', re.I)
                if exported_pattern.search(manifest):
                    vulnerabilities.append(
                        SecurityVulnerability(
                            id="BIN-EXPORTED",
                            title="Exported Components Detected",
                            description="The app has exported components that may be accessible "
                            "by other applications.",
                            owasp_category=OWASPMobileTop10.M3_INSECURE_AUTH,
                            risk_level=RiskLevel.MEDIUM,
                            cvss_score=5.5,
                            cwe_ids=[926],  # CWE-926: Improper Export of Android Components
                            location="AndroidManifest.xml",
                            evidence='android:exported="true" found',
                            remediation="Review exported components and add proper permission checks.",
                            references=[],
                        )
                    )

        except subprocess.TimeoutExpired:
            logger.error("APK analysis timed out")
        except FileNotFoundError:
            logger.warning("apktool not found, skipping APK analysis")
        except Exception as e:
            logger.error(f"APK analysis failed: {e}")
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

        return vulnerabilities

    def analyze_native_libraries(self, lib_path: Path) -> List[SecurityVulnerability]:
        """Analyze native libraries (.so files) for security features"""
        vulnerabilities = []

        try:
            # Use readelf to check security features
            result = subprocess.run(["readelf", "-h", "-l", str(lib_path)], capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                output = result.stdout

                # Check for PIE
                if "DYN (Shared object file)" not in output and "DYN (Position-Independent" not in output:
                    vulnerabilities.append(
                        SecurityVulnerability(
                            id=f"BIN-NO-PIE-{lib_path.name[:20]}",
                            title="Binary Not Position Independent",
                            description=f"Native library {lib_path.name} is not compiled as PIE, "
                            "making ASLR less effective.",
                            owasp_category=OWASPMobileTop10.M7_INSUFFICIENT_BINARY_PROTECTION,
                            risk_level=RiskLevel.MEDIUM,
                            cvss_score=5.0,
                            cwe_ids=[119],
                            location=str(lib_path),
                            evidence="Binary not compiled with -fPIE",
                            remediation="Compile native libraries with -fPIE -pie flags.",
                            references=[],
                        )
                    )

                # Check for stack canaries using checksec-style analysis
                result_syms = subprocess.run(
                    ["readelf", "-s", str(lib_path)], capture_output=True, text=True, timeout=30
                )

                if "__stack_chk_fail" not in result_syms.stdout:
                    vulnerabilities.append(
                        SecurityVulnerability(
                            id=f"BIN-NO-CANARY-{lib_path.name[:20]}",
                            title="Stack Canaries Not Enabled",
                            description=f"Native library {lib_path.name} does not have stack canaries, "
                            "making it vulnerable to stack buffer overflows.",
                            owasp_category=OWASPMobileTop10.M7_INSUFFICIENT_BINARY_PROTECTION,
                            risk_level=RiskLevel.HIGH,
                            cvss_score=7.0,
                            cwe_ids=[121],  # CWE-121: Stack-based Buffer Overflow
                            location=str(lib_path),
                            evidence="__stack_chk_fail symbol not found",
                            remediation="Compile with -fstack-protector-strong flag.",
                            references=[],
                        )
                    )

        except FileNotFoundError:
            logger.warning("readelf not found, skipping native library analysis")
        except Exception as e:
            logger.error(f"Native library analysis failed: {e}")

        return vulnerabilities


# ============================================================================
# Privacy Compliance Checker
# ============================================================================
