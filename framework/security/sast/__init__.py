"""
SAST analyzers (split out of the former sast_analyzer god file).

One module per analyzer; re-exports the full surface so existing
`from framework.security.sast_analyzer import X` imports keep working via the
thin sast_analyzer.py shim.
"""

from framework.security.sast.base import (
    VulnerabilityType,
    Severity,
    TaintSource,
    TaintSink,
    TaintFlow,
    SASTFinding,
    SASTResult,
)
from framework.security.sast.taint import TaintAnalyzer
from framework.security.sast.control_flow import ControlFlowAnalyzer
from framework.security.sast.crypto import CryptoAnalyzer
from framework.security.sast.insecure_api import InsecureAPIAnalyzer
from framework.security.sast.android_manifest import AndroidManifestAnalyzer
from framework.security.sast.ios_plist import IOSPlistAnalyzer
from framework.security.sast.analyzer import SASTAnalyzer

__all__ = [
    "VulnerabilityType",
    "Severity",
    "TaintSource",
    "TaintSink",
    "TaintFlow",
    "SASTFinding",
    "SASTResult",
    "TaintAnalyzer",
    "ControlFlowAnalyzer",
    "CryptoAnalyzer",
    "InsecureAPIAnalyzer",
    "AndroidManifestAnalyzer",
    "IOSPlistAnalyzer",
    "SASTAnalyzer",
]
