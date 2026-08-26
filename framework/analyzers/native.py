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
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, List, Optional, Tuple, cast

logger = logging.getLogger(__name__)


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


#: The minimum ``mobiscout_core`` version this framework's ABI expects. Bump it — and
#: ``rust_core/Cargo.toml``'s ``version`` — together with any incompatible change to the Rust
#: surface (e.g. the #462 ``scan_lines`` signature). An older installed wheel is then treated
#: as absent (with one warning) rather than failing every call into the silent Python path.
_MIN_NATIVE_VERSION = (0, 2, 0)

_warned_native = False


def _warn_once_native(message: str) -> None:
    """Log a native-fallback warning at most once per process (a per-line scan mustn't spam)."""
    global _warned_native
    if not _warned_native:
        _warned_native = True
        logger.warning("%s", message)


def _version_tuple(v: str) -> Tuple[int, int, int]:
    """Parse a version to a 3-tuple for ABI comparison: ``"0.2.0"`` → ``(0, 2, 0)``.

    Pads to three components so a 2-part ``"0.2"`` reads as ``(0, 2, 0)`` — not the
    shorter ``(0, 2)``, which Python would sort *below* ``(0, 2, 0)`` and wrongly
    reject — and takes each component's leading digits so a PEP 440 prerelease
    (``"0.2.0rc1"``, ``"0.2.0-dev"``) reads as its release ABI instead of failing
    ``int()`` and sorting oldest. Anything with no leading digit sorts as 0."""
    parts: List[int] = []
    for p in str(v).split(".")[:3]:
        m = re.match(r"\d+", p.strip())
        parts.append(int(m.group()) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return cast(Tuple[int, int, int], tuple(parts))


@lru_cache(maxsize=1)
def _native_core() -> Optional[Any]:
    """The imported ``mobiscout_core`` module, or ``None`` when the wheel isn't installed or is
    too old for the current ABI. A stale wheel (built before the #462 ``scan_lines`` change,
    say) would otherwise fail every call and degrade to the Python path silently — version-gate
    it up front and warn once instead of per call."""
    try:
        import mobiscout_core  # type: ignore
    except Exception:
        return None
    version = getattr(mobiscout_core, "__version__", "0.0.0")
    if _version_tuple(version) < _MIN_NATIVE_VERSION:
        _warn_once_native(
            f"mobiscout_core {version} is older than the required "
            f"{'.'.join(map(str, _MIN_NATIVE_VERSION))} — rebuild the wheel (maturin develop). "
            "Using the Python fallback."
        )
        return None
    return mobiscout_core


def native_available() -> bool:
    """Whether the Rust acceleration is installed, importable, and ABI-compatible."""
    return _native_core() is not None


def backend_name() -> str:
    """``"rust"`` when the native core is active, otherwise ``"python"``."""
    return "rust" if native_available() else "python"


def native_version() -> Optional[str]:
    """The active native core's version string, or ``None`` when the Python fallback is in use."""
    core = _native_core()
    return getattr(core, "__version__", None) if core is not None else None


def scan_lines(contents: List[str], patterns: List[str], ignore_case: bool = False) -> List[Tuple[int, int, int]]:
    """Scan file ``contents`` for regex ``patterns`` — the CPU-hot part of SAST.

    Returns one ``(file_index, line_number, rule_index)`` tuple per matching (line, rule),
    ``line_number`` 1-based. Uses the Rust ``RegexSet`` scanner when available (all rules
    matched in one DFA pass, files scanned in parallel — ~35x on a real repo); otherwise a
    pure-Python compiled-regex fallback. Results are **identical** either way: the lines are
    split here once (``str.splitlines()``, the same boundaries the analyzers number by) and
    passed to whichever backend, so neither re-splits.
    """
    lines_per_file = [content.splitlines() for content in contents]
    core = _native_core()
    if core is not None and hasattr(core, "scan_lines"):
        try:
            return cast(List[Tuple[int, int, int]], core.scan_lines(lines_per_file, list(patterns), ignore_case))
        except BaseException as e:  # noqa: BLE001 — a Rust panic isn't an Exception; Ctrl-C re-raised
            # A pattern the Rust regex crate can't compile (e.g. a negative lookahead) degrades
            # to Python. (A stale-ABI wheel is already screened out by _native_core's version
            # gate.) BaseException because a panic in the core arrives as PanicException, which
            # does not subclass Exception and would otherwise escape this seam.
            # Warn once so it doesn't silently cost the ~35x — results stay correct.
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            _warn_once_native(f"Rust scan_lines failed, using the Python fallback: {e}")
    return _scan_lines_py(lines_per_file, patterns, ignore_case)


def _scan_lines_py(
    lines_per_file: List[List[str]], patterns: List[str], ignore_case: bool
) -> List[Tuple[int, int, int]]:
    """Pure-Python reference for :func:`scan_lines` (compiled regex, one search per rule),
    over the already-split lines — same input the Rust path gets, so the two agree exactly."""
    flags = re.IGNORECASE if ignore_case else 0
    compiled = [re.compile(p, flags) for p in patterns]
    out: List[Tuple[int, int, int]] = []
    for file_idx, lines in enumerate(lines_per_file):
        for line_no, line in enumerate(lines, 1):
            for rule_idx, rx in enumerate(compiled):
                if rx.search(line):
                    out.append((file_idx, line_no, rule_idx))
    return out


def analyze_source_complexity(source: str, language: str = "python") -> SourceComplexity:
    """Complexity metrics for a source string.

    Uses the Rust core when available (fast, multi-language); otherwise the pure-Python
    fallback. Any error from the native path (an unsupported-language build, an ABI
    mismatch) degrades to the fallback rather than propagating to the caller.

    The two backends are NOT identical here (unlike :func:`scan_lines`): the Rust core parses
    with real tree-sitter grammars, the fallback uses the stdlib ``ast`` (exact for Python)
    or a coarse keyword heuristic (other languages). ``cyclomatic_complexity`` /
    ``lines_of_code`` / counts agree, but ``cognitive_complexity`` and ``max_nesting_depth``
    (and thus ``risk_level`` near a band edge) can differ. The wheel is mandatory in the
    shipped engine, so users always get the precise Rust numbers; the divergence is only
    visible in a dev checkout without the wheel built.
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
        except BaseException as exc:  # noqa: BLE001 — see below; Ctrl-C is re-raised
            # A panic inside the Rust core surfaces as pyo3_runtime.PanicException, which
            # subclasses BaseException — so `except Exception` alone lets it escape and
            # crashes the caller, defeating the point of this seam (degrade to Python, never
            # fail because the optional accelerator misbehaved). Interrupts still propagate.
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
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
