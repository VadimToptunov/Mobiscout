"""Taint analysis (split from sast_analyzer; see sast/base.py)."""

import ast
from pathlib import Path
from typing import Dict, List, Optional

from framework.security.sast.base import (
    VulnerabilityType,
    TaintSource,
    TaintSink,
    TaintFlow,
)

# Python taint sources: user-controllable / external inputs. Keys are matched
# against a call's dotted name (input, requests.get) or a bare attribute access
# (request.args, os.environ).
_PY_SOURCES: Dict[str, str] = {
    "input": "user_input",
    "request.args": "user_input",
    "request.form": "user_input",
    "request.data": "user_input",
    "request.json": "user_input",
    "request.values": "user_input",
    "request.cookies": "user_input",
    "request.headers": "user_input",
    "sys.argv": "user_input",
    "os.environ": "environment",
    "os.getenv": "environment",
    "urlopen": "network",
    "requests.get": "network",
    "requests.post": "network",
}

# Python taint sinks. Method sinks (execute, rawquery) match on the final
# attribute name; module/function sinks (os.system, eval) on the dotted name.
_PY_SINKS: Dict[str, VulnerabilityType] = {
    "execute": VulnerabilityType.SQL_INJECTION,
    "executemany": VulnerabilityType.SQL_INJECTION,
    "os.system": VulnerabilityType.COMMAND_INJECTION,
    "subprocess.call": VulnerabilityType.COMMAND_INJECTION,
    "subprocess.run": VulnerabilityType.COMMAND_INJECTION,
    "subprocess.Popen": VulnerabilityType.COMMAND_INJECTION,
    "eval": VulnerabilityType.COMMAND_INJECTION,
    "exec": VulnerabilityType.COMMAND_INJECTION,
    "open": VulnerabilityType.PATH_TRAVERSAL,
    "pickle.load": VulnerabilityType.UNSAFE_DESERIALIZATION,
    "pickle.loads": VulnerabilityType.UNSAFE_DESERIALIZATION,
    "yaml.load": VulnerabilityType.UNSAFE_DESERIALIZATION,
}


def _dotted(node: ast.AST) -> str:
    """Render a Name/Attribute chain to a dotted string ("os.environ")."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _target_names(target: ast.AST) -> List[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: List[str] = []
        for elt in target.elts:
            names.extend(_target_names(elt))
        return names
    return []


class TaintAnalyzer:
    """
    Taint Analysis Engine.

    For Python, tracks intra-procedural data flow via the AST: a variable
    becomes tainted when assigned from a source (or from another tainted
    variable), and a flow is reported when a tainted value reaches a sink. This
    replaces the old line-local substring matching, which both missed real flows
    and flagged unrelated lines. Non-Python files fall back to source/sink
    substring detection.
    """

    def __init__(self):
        # Full multi-language source/sink patterns for the substring fallback
        # (non-Python files). Python files use the AST engine and _PY_* above.
        self.sources = {
            "input": "user_input",
            "request.args": "user_input",
            "request.form": "user_input",
            "request.data": "user_input",
            "request.json": "user_input",
            "request.cookies": "user_input",
            "request.headers": "user_input",
            "sys.argv": "user_input",
            "os.environ": "environment",
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
        self.sinks = {
            "execute(": VulnerabilityType.SQL_INJECTION,
            "rawQuery(": VulnerabilityType.SQL_INJECTION,
            "execSQL(": VulnerabilityType.SQL_INJECTION,
            "Runtime.getRuntime().exec(": VulnerabilityType.COMMAND_INJECTION,
            "FileInputStream(": VulnerabilityType.PATH_TRAVERSAL,
            "FileOutputStream(": VulnerabilityType.PATH_TRAVERSAL,
            "loadUrl(": VulnerabilityType.XSS,
            "evaluateJavascript(": VulnerabilityType.XSS,
            "Log.d(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "Log.e(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "NSLog(": VulnerabilityType.SENSITIVE_DATA_LOG,
            "ObjectInputStream(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "readObject(": VulnerabilityType.UNSAFE_DESERIALIZATION,
            "NSKeyedUnarchiver": VulnerabilityType.UNSAFE_DESERIALIZATION,
        }
        self.tainted_vars: Dict[str, TaintSource] = {}

    # ------------------------------------------------------------------ Python
    def _find_source(self, node: ast.AST) -> Optional[str]:
        """Return the source_type if the expression subtree reads a source."""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                stype = _PY_SOURCES.get(_dotted(sub.func))
                if stype:
                    return stype
            if isinstance(sub, ast.Attribute):
                stype = _PY_SOURCES.get(_dotted(sub))
                if stype:
                    return stype
            if isinstance(sub, ast.Name):
                stype = _PY_SOURCES.get(sub.id)
                if stype:
                    return stype
        return None

    def _referenced_tainted(self, node: ast.AST, tainted: Dict[str, TaintSource]) -> Optional[str]:
        """Return the name of a tainted variable referenced in the subtree."""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in tainted:
                return sub.id
        return None

    @staticmethod
    def _sink_of(call: ast.Call) -> Optional[VulnerabilityType]:
        dotted = _dotted(call.func)
        if dotted in _PY_SINKS:
            return _PY_SINKS[dotted]
        if isinstance(call.func, ast.Attribute):  # method call: match final name
            return _PY_SINKS.get(call.func.attr)
        return None

    def _analyze_python(self, content: str, file_path: Path) -> List[TaintFlow]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        tainted: Dict[str, TaintSource] = {}
        flows: List[TaintFlow] = []

        # Process assignments and calls in source order so taint propagates.
        nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.Call))]
        nodes.sort(key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))

        for node in nodes:
            if isinstance(node, ast.Assign):
                stype = self._find_source(node.value)
                src: Optional[TaintSource] = None
                if stype:
                    src = TaintSource("<expr>", str(file_path), node.lineno, stype)
                else:
                    ref = self._referenced_tainted(node.value, tainted)
                    if ref:
                        src = tainted[ref]  # propagate
                if src:
                    for target in node.targets:
                        for name in _target_names(target):
                            tainted[name] = TaintSource(name, src.location, node.lineno, src.source_type)
            else:  # ast.Call
                vuln = self._sink_of(node)
                if not vuln:
                    continue
                args = list(node.args) + [kw.value for kw in node.keywords]
                for arg in args:
                    ref = self._referenced_tainted(arg, tainted)
                    stype = None if ref else self._find_source(arg)
                    source = (
                        tainted[ref]
                        if ref
                        else (TaintSource("<inline>", str(file_path), node.lineno, stype) if stype else None)
                    )
                    if source is not None:
                        sink = TaintSink(_dotted(node.func) or "<sink>", str(file_path), node.lineno, vuln.value)
                        flows.append(
                            TaintFlow(source=source, sink=sink, path=[ref or "<inline>"], vulnerability_type=vuln)
                        )
                        break
        return flows

    # ----------------------------------------------------------------- generic
    def _analyze_generic(self, content: str, file_path: Path) -> List[TaintFlow]:
        """Substring fallback for non-Python languages (Kotlin/Swift/Java)."""
        import re

        flows: List[TaintFlow] = []
        tainted: Dict[str, TaintSource] = {}
        for i, line in enumerate(content.splitlines(), 1):
            for pattern, stype in self.sources.items():
                if pattern in line:
                    m = re.search(r"(\w+)\s*=", line)
                    if m:
                        tainted[m.group(1)] = TaintSource(m.group(1), str(file_path), i, stype)
            for pattern, vuln in self.sinks.items():
                if pattern in line:
                    for name, source in tainted.items():
                        if re.search(rf"\b{re.escape(name)}\b", line):
                            sink = TaintSink(pattern, str(file_path), i, vuln.value)
                            flows.append(TaintFlow(source=source, sink=sink, path=[name], vulnerability_type=vuln))
        return flows

    def analyze_file(self, file_path: Path) -> List[TaintFlow]:
        """Analyze a file for taint flows (AST for .py, substring otherwise)."""
        self.tainted_vars = {}
        try:
            content = Path(file_path).read_text()
        except (OSError, UnicodeDecodeError):
            return []
        if str(file_path).endswith(".py"):
            return self._analyze_python(content, Path(file_path))
        return self._analyze_generic(content, Path(file_path))
