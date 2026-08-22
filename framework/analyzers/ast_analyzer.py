"""
Deep AST Analysis Module

Provides deep Abstract Syntax Tree analysis for complex logic extraction.
Currently supports Python AST analysis as a foundation.
Future: Kotlin/Java AST parsing, Swift AST parsing.
"""

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any, Union

from framework.analyzers.native import SourceComplexity, analyze_source_complexity, backend_name

logger = logging.getLogger(__name__)


@dataclass
class FunctionComplexity:
    """Represents complexity metrics for a function"""

    name: str
    cyclomatic_complexity: int
    cognitive_complexity: int
    lines_of_code: int
    num_parameters: int
    num_returns: int
    num_branches: int
    num_loops: int
    nested_depth: int
    source_file: Optional[str] = None


@dataclass
class DataFlow:
    """Represents data flow in code"""

    variable: str
    source: str  # where the data comes from
    transformations: List[str] = field(default_factory=list)
    sinks: List[str] = field(default_factory=list)  # where data ends up
    source_file: Optional[str] = None


@dataclass
class ControlFlow:
    """Represents control flow graph node"""

    node_type: str  # if, for, while, try, etc.
    condition: Optional[str] = None
    branches: List[str] = field(default_factory=list)
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)


class ASTAnalyzer:
    """
    Deep AST analyzer for complex logic extraction

    Currently focuses on Python AST as a proof of concept.
    Can be extended to Kotlin/Java/Swift using appropriate parsers.
    """

    def __init__(self, source_path: Path) -> None:
        self.source_path = Path(source_path)
        self.functions: List[FunctionComplexity] = []
        self.data_flows: List[DataFlow] = []
        self.control_flows: List[ControlFlow] = []

    def analyze_python(self) -> Dict[str, Any]:
        """
        Analyze Python source code using AST

        Returns:
            Dict with complexity metrics, data flows, control flows
        """
        for py_file in self.source_path.rglob("*.py"):
            if self._is_test_file(py_file) or "__pycache__" in str(py_file):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(py_file))

                self._analyze_tree(tree, py_file)

            except SyntaxError:
                continue
            except Exception as e:
                print(f"Warning: Could not analyze {py_file}: {e}")

        return {
            "functions": [self._function_to_dict(f) for f in self.functions],
            "data_flows": [self._dataflow_to_dict(df) for df in self.data_flows],
            "control_flows": [self._controlflow_to_dict(cf) for cf in self.control_flows],
            "summary": {
                "total_functions": len(self.functions),
                "high_complexity_functions": len([f for f in self.functions if f.cyclomatic_complexity > 10]),
                "average_complexity": (
                    sum(f.cyclomatic_complexity for f in self.functions) / len(self.functions) if self.functions else 0
                ),
                # Which complexity backend is active: "rust" when the mobiscout_core
                # accelerator wheel is installed, else "python".
                "complexity_backend": backend_name(),
            },
        }

    def module_complexity(self, source: str, language: str = "python") -> SourceComplexity:
        """Whole-source complexity for a single file's text, in any supported language.

        Routed through the optional Rust accelerator (`mobiscout_core`) when installed,
        with a pure-Python fallback otherwise — so this works with or without the native
        build, and gains multi-language precision + speed when it's present."""
        return analyze_source_complexity(source, language)

    @staticmethod
    def _is_test_file(py_file: Path) -> bool:
        """Whether a path is a real pytest test file.

        Only the file name decides this: ``test_*.py`` or ``*_test.py``. Matching
        the substring "test" anywhere in the path (the previous behaviour) wrongly
        skipped files under pytest temp dirs and any path containing words like
        "latest"/"greatest", so complexity analysis found zero functions.
        """
        name = py_file.name
        return name.startswith("test_") or name.endswith("_test.py")

    def _analyze_tree(self, tree: ast.AST, file_path: Path) -> None:
        """Analyze AST tree for functions and complexity"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._analyze_function(node, file_path)

    def _analyze_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], file_path: Path) -> None:
        """Analyze a function node for complexity metrics"""
        # Calculate cyclomatic complexity
        complexity = self._calculate_complexity(node)

        # Calculate cognitive complexity
        cognitive = self._calculate_cognitive_complexity(node)

        # Count various metrics
        num_returns = sum(1 for n in ast.walk(node) if isinstance(n, ast.Return))
        # Check if ast.Match exists (Python 3.10+)
        match_types = (ast.If, ast.IfExp)
        if hasattr(ast, "Match"):
            match_types = (ast.If, ast.IfExp, ast.Match)  # type: ignore
        num_branches = sum(1 for n in ast.walk(node) if isinstance(n, match_types))
        num_loops = sum(1 for n in ast.walk(node) if isinstance(n, (ast.For, ast.While, ast.AsyncFor)))

        # Calculate nested depth
        nested_depth = self._calculate_nested_depth(node)

        # Count lines
        if (
            hasattr(node, "end_lineno")
            and hasattr(node, "lineno")
            and node.end_lineno is not None
            and node.lineno is not None
        ):
            loc = node.end_lineno - node.lineno + 1
        else:
            loc = 0

        func_complexity = FunctionComplexity(
            name=node.name,
            cyclomatic_complexity=complexity,
            cognitive_complexity=cognitive,
            lines_of_code=loc,
            num_parameters=len(node.args.args),
            num_returns=num_returns,
            num_branches=num_branches,
            num_loops=num_loops,
            nested_depth=nested_depth,
            source_file=str(file_path),
        )

        self.functions.append(func_complexity)

    def _calculate_complexity(self, node: ast.AST) -> int:
        """Calculate McCabe cyclomatic complexity"""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, (ast.ExceptHandler,)):
                complexity += 1

        return complexity

    def _calculate_cognitive_complexity(self, node: ast.AST) -> int:
        """Calculate cognitive complexity (more human-oriented)"""

        def cognitive_walk(node: ast.AST, depth: int = 0) -> int:
            score = 0

            if isinstance(node, (ast.If, ast.For, ast.While, ast.Try)):
                score += 1 + depth
            elif isinstance(node, ast.BoolOp):
                score += len(node.values) - 1

            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.If, ast.For, ast.While, ast.Try)):
                    score += cognitive_walk(child, depth + 1)
                else:
                    score += cognitive_walk(child, depth)

            return score

        return cognitive_walk(node)

    def _calculate_nested_depth(self, node: ast.AST) -> int:
        """Calculate maximum nesting depth"""

        def depth_walk(node: ast.AST, current_depth: int = 0) -> int:
            max_depth = current_depth

            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                    child_depth = depth_walk(child, current_depth + 1)
                    max_depth = max(max_depth, child_depth)
                else:
                    child_depth = depth_walk(child, current_depth)
                    max_depth = max(max_depth, child_depth)

            return max_depth

        return depth_walk(node)

    def _function_to_dict(self, func: FunctionComplexity) -> Dict[str, Any]:
        """Convert FunctionComplexity to dict"""
        return {
            "name": func.name,
            "cyclomatic_complexity": func.cyclomatic_complexity,
            "cognitive_complexity": func.cognitive_complexity,
            "lines_of_code": func.lines_of_code,
            "num_parameters": func.num_parameters,
            "num_returns": func.num_returns,
            "num_branches": func.num_branches,
            "num_loops": func.num_loops,
            "nested_depth": func.nested_depth,
            "source_file": func.source_file,
        }

    def _dataflow_to_dict(self, df: DataFlow) -> Dict[str, Any]:
        """Convert DataFlow to dict"""
        return {
            "variable": df.variable,
            "source": df.source,
            "transformations": df.transformations,
            "sinks": df.sinks,
            "source_file": df.source_file,
        }

    def _controlflow_to_dict(self, cf: ControlFlow) -> Dict[str, Any]:
        """Convert ControlFlow to dict"""
        return {
            "node_type": cf.node_type,
            "condition": cf.condition,
            "branches": cf.branches,
            "parent": cf.parent,
            "children": cf.children,
        }
