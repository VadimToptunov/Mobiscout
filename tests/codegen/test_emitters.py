"""
Golden-file + compile tests for codegen emitters.

For every registered target we assert two things, neither of which needs a
device:
  1. Output matches the committed golden file (catches accidental drift).
  2. Generated source is syntactically valid for its language (catches a
     broken template before it ever reaches a user).

Regenerate goldens after an intentional template change with:
    UPDATE_GOLDENS=1 pytest tests/codegen/test_emitters.py
"""

import os
import py_compile
from pathlib import Path

import pytest

from framework.codegen import get_emitter
from framework.codegen.ir import TestModel

GOLDEN_DIR = Path(__file__).parent / "golden"


def _check_golden(rel_path: str, content: str) -> None:
    golden = GOLDEN_DIR / rel_path
    if os.environ.get("UPDATE_GOLDENS"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(content)
        return
    assert golden.exists(), f"Missing golden file: {golden} (run with UPDATE_GOLDENS=1)"
    assert content == golden.read_text(), (
        f"Output drifted from golden {rel_path}. "
        f"If intentional, regenerate with UPDATE_GOLDENS=1."
    )


def test_python_pytest_golden(login_model: TestModel):
    out = get_emitter("python_pytest").emit(login_model)
    for path, content in out.items():
        _check_golden(f"python_pytest/{path}", content)


def test_python_pytest_compiles(login_model: TestModel, tmp_path):
    """Generated Python must be importable syntax — compile it for real."""
    out = get_emitter("python_pytest").emit(login_model)
    for path, content in out.items():
        f = tmp_path / path
        f.write_text(content)
        py_compile.compile(str(f), doraise=True)


def test_ir_roundtrip(login_model: TestModel):
    """IR must survive a JSON round-trip so fixtures stay portable."""
    restored = TestModel.from_dict(login_model.to_dict())
    assert restored.to_dict() == login_model.to_dict()
