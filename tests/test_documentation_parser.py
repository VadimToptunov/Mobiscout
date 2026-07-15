"""The code parser extracts module/class/function structure from Python source via
AST — pure, so tests feed it a source file and assert the extracted docs. Also
guards the parent-pointer fix: without it, top-level functions and constants were
silently dropped."""

from pathlib import Path

import pytest

from framework.documentation.parser import CodeParser, DocstringParser

_SRC = '''
"""Module docstring."""
import os
from pathlib import Path

MAX_RETRIES = 3
NAMES = ["a", "b"]


def top_level(x: int, name: str = "hi") -> bool:
    """A top-level function."""
    return True


class Widget(Base, Mixin):
    """A widget."""

    kind = "button"

    def __init__(self, size: int = 10) -> None:
        self.size = size

    def area(self) -> int:
        """Compute area."""
        return self.size * self.size
'''


@pytest.fixture()
def module_doc(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text(_SRC)
    return CodeParser().parse_file(f)


def test_module_docstring_and_imports(module_doc):
    assert module_doc.docstring == "Module docstring."
    assert "os" in module_doc.imports and "pathlib" in module_doc.imports


def test_top_level_function_and_constants_extracted(module_doc):
    # Regression: the parent-pointer fix — these were dropped before.
    names = {f.name for f in module_doc.functions}
    assert "top_level" in names
    assert module_doc.constants.get("MAX_RETRIES") == 3
    assert module_doc.constants.get("NAMES") == ["a", "b"]


def test_function_signature_params_and_return(module_doc):
    fn = next(f for f in module_doc.functions if f.name == "top_level")
    assert fn.return_type == "bool"
    assert fn.docstring == "A top-level function."
    params = {p["name"]: p for p in fn.parameters}
    assert params["x"]["type"] == "int"
    assert params["name"]["default"] == "hi"
    assert "-> bool" in fn.signature


def test_class_bases_methods_attributes(module_doc):
    widget = next(c for c in module_doc.classes if c.name == "Widget")
    assert widget.docstring == "A widget."
    assert set(widget.bases) == {"Base", "Mixin"}
    method_names = {m.name for m in widget.methods}
    assert {"__init__", "area"} <= method_names
    attr_names = {a["name"] for a in widget.attributes}
    assert "kind" in attr_names


def test_get_value_handles_containers(tmp_path):
    f = tmp_path / "c.py"
    f.write_text("D = {'k': 1}\nL = [1, 2, 3]\n")
    doc = CodeParser().parse_file(f)
    assert doc.constants["D"] == {"k": 1}
    assert doc.constants["L"] == [1, 2, 3]


def test_docstring_parser_google_style():
    doc = """Short description.

    Args:
        x: the x value
        y: the y value

    Returns:
        the result

    Raises:
        ValueError: on bad input
    """
    parsed = DocstringParser.parse_google_style(doc)
    assert "Short description." in str(parsed["description"])
    assert "x" in str(parsed["args"])
    assert parsed["returns"] is not None
    assert "ValueError" in str(parsed["raises"])


def test_docstring_parser_empty():
    assert DocstringParser.parse_google_style("") == {}
