"""Analyzer extracted from sast_analyzer (mechanical split; see sast/base.py)."""

import ast
import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET

from framework.security.sast.base import (
    VulnerabilityType,
    Severity,
    TaintSource,
    TaintSink,
    TaintFlow,
    SASTFinding,
    SASTResult,
)


class TaintAnalyzer:
    """
    Taint Analysis Engine

    Tracks data flow from untrusted sources to security-sensitive sinks.
    """

    def __init__(self):
        # Define taint sources (user-controllable inputs)
        self.sources = {
            # Python
            "input": "user_input",
            "request.args": "user_input",
            "request.form": "user_input",
            "request.data": "user_input",
            "request.json": "user_input",
            "request.cookies": "user_input",
            "request.headers": "user_input",
            "sys.argv": "user_input",
            "os.environ": "environment",
            "open(": "file",
            "read(": "file",
            "recv(": "network",
            "recvfrom(": "network",
            "urlopen(": "network",
            "requests.get": "network",
            "requests.post": "network",
            # Android/Kotlin
            "getIntent()": "user_input",
            "getExtras()": "user_input",
            "getStringExtra": "user_input",
            "getQueryParameter": "user_input",
            "getText()": "user_input",
            "getSharedPreferences": "storage",
            # iOS/Swift
            "UserDefaults": "storage",
            "UIPasteboard": "user_input",
            "URLComponents": "user_input",
        }

        # Define taint sinks (security-sensitive operations)
        self.sinks = {
            # SQL
            "execute(": VulnerabilityType.SQL_INJECTION,
            "executemany(": VulnerabilityType.SQL_INJECTION,
            "raw(": VulnerabilityType.SQL_INJECTION,
            "rawQuery(": VulnerabilityType.SQL_INJECTION,
            "execSQL(": VulnerabilityType.SQL_INJECTION,
            # Command
            "os.system(": VulnerabilityType.COMMAND_INJECTION,
            "subprocess.call(": VulnerabilityType.COMMAND_INJECTION,
            "subprocess.run(": VulnerabilityType.COMMAND_INJECTION,
            "subprocess.Popen(": VulnerabilityType.COMMAND_INJECTION,
            "eval(": VulnerabilityType.COMMAND_INJECTION,
            "exec(": VulnerabilityType.COMMAND_INJECTION,
            "Runtime.getRuntime().exec(": VulnerabilityType.COMMAND_INJECTION,
            # File
            "open(": VulnerabilityType.PATH_TRAVERSAL,
            "FileInputStream(": VulnerabilityType.PATH_TRAVERSAL,
            "FileOutputStream(": VulnerabilityType.PATH_TRAVERSAL,
            # XSS
            "innerHTML": VulnerabilityType.XSS,
            "document.write(": VulnerabilityType.XSS,
            "loadUrl(": VulnerabilityType.XSS,
            "evaluateJavascript(": VulnerabilityType.XSS,
            # Logging
            "print(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "Log.d(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "Log.i(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "Log.e(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "NSLog(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "logger.": VulnerabilityType.SENSITIVE_DATA_LOG,
            # Deserialization
            "pickle.load(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "pickle.loads(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "yaml.load(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "ObjectInputStream(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "readObject(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "NSKeyedUnarchiver": VulnerabilityType.UNSAFE_DESERIALIZATION,
        }

        self.tainted_vars: Dict[str, TaintSource] = {}

    def analyze_file(self, file_path: Path) -> List[TaintFlow]:
        """Analyze file for taint flows"""
        flows = []

        try:
            content = file_path.read_text()
            lines = content.splitlines()

            # Track tainted variables
            for i, line in enumerate(lines, 1):
                # Check for sources
                for source_pattern, source_type in self.sources.items():
                    if source_pattern in line:
                        # Extract variable name
                        var_match = re.search(r"(\w+)\s*=", line)
                        if var_match:
                            var_name = var_match.group(1)
                            self.tainted_vars[var_name] = TaintSource(
                                name=var_name,
                                location=str(file_path),
                                line_number=i,
                                source_type=source_type,
                            )

                # Check for sinks using tainted data
                for sink_pattern, vuln_type in self.sinks.items():
                    if sink_pattern in line:
                        # Check if any tainted variable is used
                        for var_name, source in self.tainted_vars.items():
                            if var_name in line:
                                sink = TaintSink(
                                    name=sink_pattern,
                                    location=str(file_path),
                                    line_number=i,
                                    sink_type=vuln_type.value,
                                )
                                flows.append(
                                    TaintFlow(
                                        source=source,
                                        sink=sink,
                                        path=[var_name],
                                        vulnerability_type=vuln_type,
                                    )
                                )

        except (OSError, UnicodeDecodeError):
            pass

        return flows
