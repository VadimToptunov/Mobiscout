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
import shutil
import subprocess
import re
from pathlib import Path

import pytest

from framework.codegen import available_targets, get_emitter
from framework.codegen.ir import TestModel

GOLDEN_DIR = Path(__file__).parent / "golden"

TARGET_IDS = [t.id for t in available_targets()]

# javac without the Appium/TestNG/Selenium jars on the classpath can only fail
# on dependency resolution, never on syntax. So we accept those two error
# classes and treat anything else (';' expected, illegal start, ...) as a real
# syntax defect in the generated source.
_JAVAC_DEP_ERROR = re.compile(
    r"error:\s+(cannot find symbol|package \S+ does not exist)"
)


def _java_syntax_ok(java_file: Path) -> None:
    """Assert generated Java is syntactically valid, tolerating missing deps."""
    javac = shutil.which("javac")
    if not javac:
        pytest.skip("javac not available — skipping Java syntax gate")
    proc = subprocess.run(
        [javac, "-d", str(java_file.parent / "_out"), str(java_file)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return  # fully compiled (deps present)
    bad = [
        line
        for line in proc.stderr.splitlines()
        if "error:" in line and not _JAVAC_DEP_ERROR.search(line)
    ]
    assert not bad, "Generated Java has syntax errors:\n" + "\n".join(bad)


def _js_syntax_ok(js_file: Path) -> None:
    """Assert generated JavaScript parses. node --check is syntax-only, so it
    needs none of the WebdriverIO/Mocha globals at runtime."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available — skipping JS syntax gate")
    proc = subprocess.run(
        [node, "--check", str(js_file)], capture_output=True, text=True
    )
    assert proc.returncode == 0, "Generated JS has syntax errors:\n" + proc.stderr


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
def test_generated_source_is_valid(target_id: str, login_model: TestModel, tmp_path):
    """Every generated code file must be syntactically valid for its language.
    Python is compiled with py_compile; Java is checked with javac (tolerating
    absent third-party jars); non-code artifacts like .feature are skipped."""
    out = get_emitter(target_id).emit(login_model)
    checked = 0
    for path, content in out.items():
        f = tmp_path / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
        if path.endswith(".py"):
            py_compile.compile(str(f), doraise=True)
            checked += 1
        elif path.endswith(".java"):
            _java_syntax_ok(f)
            checked += 1
        elif path.endswith(".js"):
            _js_syntax_ok(f)
            checked += 1
    assert checked, f"{target_id} produced no source to validate"


def test_ir_roundtrip(login_model: TestModel):
    """IR must survive a JSON round-trip so fixtures stay portable."""
    restored = TestModel.from_dict(login_model.to_dict())
    assert restored.to_dict() == login_model.to_dict()
