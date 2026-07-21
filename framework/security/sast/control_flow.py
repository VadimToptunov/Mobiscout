"""Analyzer extracted from sast_analyzer (mechanical split; see sast/base.py)."""

import ast
import hashlib
import json
import logging
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

logger = logging.getLogger(__name__)


class ControlFlowAnalyzer:
    """
    Control Flow Analysis

    Analyzes control flow for security issues.
    """

    def analyze_python(self, file_path: Path) -> List[SASTFinding]:
        """Analyze Python file control flow"""
        findings = []

        try:
            content = file_path.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                # Check for unreachable code after return/raise
                if isinstance(node, ast.FunctionDef):
                    findings.extend(self._check_unreachable_code(node, file_path))

                # Check for exception handling issues
                if isinstance(node, ast.Try):
                    findings.extend(self._check_exception_handling(node, file_path))

        except (SyntaxError, OSError, UnicodeDecodeError) as e:
            # Unparseable/unreadable source is silently absent from the scan results.
            logger.debug("SAST control-flow: skipped %s: %s", file_path, e)

        return findings

    def _check_unreachable_code(self, func: ast.FunctionDef, file_path: Path) -> List[SASTFinding]:
        """Check for unreachable code"""
        findings = []

        for i, stmt in enumerate(func.body):
            if isinstance(stmt, (ast.Return, ast.Raise)):
                # Check if there's code after return/raise
                if i < len(func.body) - 1:
                    next_stmt = func.body[i + 1]
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.DEAD_CODE,
                            severity=Severity.INFO,
                            title="Unreachable code detected",
                            description=f"Code after return/raise statement in function '{func.name}' is unreachable",
                            file_path=str(file_path),
                            line_number=next_stmt.lineno,
                            recommendation="Remove unreachable code or fix control flow logic",
                            cwe_id="CWE-561",
                        )
                    )

        return findings

    def _check_exception_handling(self, try_node: ast.Try, file_path: Path) -> List[SASTFinding]:
        """Check exception handling issues"""
        findings = []

        for handler in try_node.handlers:
            # Bare except clause
            if handler.type is None:
                findings.append(
                    SASTFinding(
                        vulnerability_type=VulnerabilityType.DEAD_CODE,
                        severity=Severity.MEDIUM,
                        title="Bare except clause",
                        description="Catching all exceptions can hide bugs and make debugging difficult",
                        file_path=str(file_path),
                        line_number=handler.lineno,
                        recommendation="Catch specific exceptions instead of using bare except",
                        cwe_id="CWE-396",
                    )
                )

            # Empty except block
            if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                findings.append(
                    SASTFinding(
                        vulnerability_type=VulnerabilityType.DEAD_CODE,
                        severity=Severity.MEDIUM,
                        title="Empty exception handler",
                        description="Empty exception handler silently swallows errors",
                        file_path=str(file_path),
                        line_number=handler.lineno,
                        recommendation="Handle the exception or log it, don't silently ignore",
                        cwe_id="CWE-390",
                    )
                )

        return findings
