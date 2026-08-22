"""Optional Rust acceleration for source-complexity analysis.

The Rust core (``mobiscout_core``, built from ``rust_core/`` and installed as a wheel)
exposes a fast, multi-language complexity analyzer over PyO3. It is **optional**: when
the wheel isn't installed, every call falls back to a pure-Python implementation, so
nothing in the framework depends on the native build being present. This module is the
single seam between the two — import it, call :func:`analyze_source_complexity`, and it
uses whichever backend is available.

The Python fallback is exact for Python source (via the stdlib ``ast``) and a coarse
keyword/brace heuristic for other languages; the Rust core is what makes the other
languages precise (and everything fast).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional


@dataclass
class SourceComplexity:
    """Module-level complexity of a source string — the shape both backends return."""

    cyclomatic_complexity: int
    cognitive_complexity: int
    max_nesting_depth: int
    lines_of_code: int
    function_count: int
    class_count: int

    @property
    def risk_level(self) -> str:
        """A coarse risk band, matching the Rust core's ``ComplexityMetrics.risk_level``."""
        if self.cyclomatic_complexity > 20 or self.cognitive_complexity > 30:
            return "high"
        if self.cyclomatic_complexity > 10 or self.cognitive_complexity > 15:
            return "medium"
        return "low"


@lru_cache(maxsize=1)
def _native_core() -> Optional[Any]:
    """The imported ``mobiscout_core`` module, or ``None`` when the wheel isn't installed."""
    try:
        import mobiscout_core  # type: ignore

        return mobiscout_core
    except Exception:
        return None


def native_available() -> bool:
    """Whether the Rust acceleration is installed and importable."""
    return _native_core() is not None


def backend_name() -> str:
    """``"rust"`` when the native core is active, otherwise ``"python"``."""
    return "rust" if native_available() else "python"


def analyze_source_complexity(source: str, language: str = "python") -> SourceComplexity:
    """Complexity metrics for a source string.

    Uses the Rust core when available (fast, multi-language); otherwise the pure-Python
    fallback. Any error from the native path (an unsupported-language build, an ABI
    mismatch) degrades to the fallback rather than propagating to the caller.
    """
    core = _native_core()
    if core is not None:
        try:
            m = core.RustAstAnalyzer().analyze_source(source, language)
            return SourceComplexity(
                cyclomatic_complexity=m.cyclomatic_complexity,
                cognitive_complexity=m.cognitive_complexity,
                max_nesting_depth=m.max_nesting_depth,
                lines_of_code=m.lines_of_code,
                function_count=m.function_count,
                class_count=m.class_count,
            )
        except Exception:
            pass
    return _python_fallback(source, language)


def _python_fallback(source: str, language: str) -> SourceComplexity:
    if language.lower() in ("python", "py"):
        return _python_ast_complexity(source)
    return _heuristic_complexity(source)


def _loc(source: str) -> int:
    """Non-blank source lines."""
    return sum(1 for line in source.splitlines() if line.strip())


def _python_ast_complexity(source: str) -> SourceComplexity:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _heuristic_complexity(source)

    cyclomatic = 1
    functions = 0
    classes = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
            cyclomatic += 1
        elif isinstance(node, ast.BoolOp):
            cyclomatic += len(node.values) - 1
        elif isinstance(node, ast.ExceptHandler):
            cyclomatic += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions += 1
        elif isinstance(node, ast.ClassDef):
            classes += 1

    return SourceComplexity(
        cyclomatic_complexity=cyclomatic,
        cognitive_complexity=_cognitive(tree),
        max_nesting_depth=_max_nesting(tree),
        lines_of_code=_loc(source),
        function_count=functions,
        class_count=classes,
    )


#: AST nodes that open a new nesting level for cognitive/nesting scoring.
_NESTING = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)


def _max_nesting(tree: ast.AST) -> int:
    def depth(node: ast.AST, current: int) -> int:
        best = current
        for child in ast.iter_child_nodes(node):
            step = 1 if isinstance(child, _NESTING) else 0
            best = max(best, depth(child, current + step))
        return best

    return depth(tree, 0)


def _cognitive(tree: ast.AST) -> int:
    """Cognitive complexity: each control structure costs 1 + its nesting level."""
    total = 0

    def visit(node: ast.AST, level: int) -> None:
        nonlocal total
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _NESTING):
                total += 1 + level
                visit(child, level + 1)
            else:
                visit(child, level)

    visit(tree, 0)
    return total


def _heuristic_complexity(source: str) -> SourceComplexity:
    """A language-agnostic keyword/brace heuristic — the fallback for non-Python source
    when the native core isn't installed. Approximate by design."""
    branches = len(re.findall(r"\b(?:if|elif|for|while|case|catch|when)\b", source))
    conj = len(re.findall(r"&&|\|\||\band\b|\bor\b", source))
    functions = len(re.findall(r"\b(?:def|fun|func|function)\b", source))
    classes = len(re.findall(r"\b(?:class|struct|interface|object|protocol|enum)\b", source))
    return SourceComplexity(
        cyclomatic_complexity=1 + branches + conj,
        cognitive_complexity=branches + conj,
        max_nesting_depth=_brace_nesting(source),
        lines_of_code=_loc(source),
        function_count=functions,
        class_count=classes,
    )


def _brace_nesting(source: str) -> int:
    depth = best = 0
    for ch in source:
        if ch in "{(":
            depth += 1
            best = max(best, depth)
        elif ch in "})":
            depth = max(0, depth - 1)
    return best
