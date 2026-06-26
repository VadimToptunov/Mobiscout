"""
Golden-file + compile tests for codegen emitters.

For every registered target we assert two things, neither of which needs a
device:
  1. Output matches the committed golden files (catches accidental drift).
  2. Generated *source* is syntactically valid (catches a broken template
     before it ever reaches a user). Python files are compiled; non-code
     artifacts like .feature are only golden-checked.

Regenerate goldens after an intentional template change with:
    UPDATE_GOLDENS=1 pytest tests/codegen/test_emitters.py
"""

import os
import py_compile
from pathlib import Path

import pytest

from framework.codegen import available_targets, get_emitter
from framework.codegen.ir import TestModel

GOLDEN_DIR = Path(__file__).parent / "golden"

# Targets whose generated Python should additionally be compiled.
TARGET_IDS = [t.id for t in available_targets()]


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


@pytest.mark.parametrize("target_id", TARGET_IDS)
def test_emitter_golden(target_id: str, login_model: TestModel):
    out = get_emitter(target_id).emit(login_model)
    assert out, f"{target_id} emitted no files"
    for path, content in out.items():
        _check_golden(f"{target_id}/{path}", content)


@pytest.mark.parametrize("target_id", TARGET_IDS)
def test_generated_python_compiles(target_id: str, login_model: TestModel, tmp_path):
    """Every generated .py must be valid Python — compile it for real."""
    out = get_emitter(target_id).emit(login_model)
    compiled_any = False
    for path, content in out.items():
        f = tmp_path / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
        if path.endswith(".py"):
            py_compile.compile(str(f), doraise=True)
            compiled_any = True
    assert compiled_any, f"{target_id} produced no Python to compile"


def test_ir_roundtrip(login_model: TestModel):
    """IR must survive a JSON round-trip so fixtures stay portable."""
    restored = TestModel.from_dict(login_model.to_dict())
    assert restored.to_dict() == login_model.to_dict()
