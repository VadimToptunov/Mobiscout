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
from framework.codegen.ir import Platform, TestModel

GOLDEN_DIR = Path(__file__).parent / "golden"

TARGET_IDS = [t.id for t in available_targets()]

# javac without the Appium/TestNG/Selenium jars on the classpath can only fail
# on dependency resolution, never on syntax. So we accept those two error
# classes and treat anything else (';' expected, illegal start, ...) as a real
# syntax defect in the generated source.
_JAVAC_DEP_ERROR = re.compile(r"error:\s+(cannot find symbol|package \S+ does not exist)")


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
    bad = [line for line in proc.stderr.splitlines() if "error:" in line and not _JAVAC_DEP_ERROR.search(line)]
    assert not bad, "Generated Java has syntax errors:\n" + "\n".join(bad)


# kotlinc, like javac, cannot resolve the Appium/JUnit jars here, so it will
# report dependency errors. We can't enumerate every dependency-error phrasing
# reliably, so this gate is safe-by-default: it fails ONLY on recognised Kotlin
# syntax-error markers (a broken template), and tolerates everything else.
_KOTLINC_SYNTAX_MARKERS = (
    "expecting",
    "unexpected",
    "mismatched",
    "illegal",
    "missing",
)


def _kotlin_syntax_ok(kt_file: Path) -> None:
    """Assert generated Kotlin has no syntax errors, tolerating missing deps."""
    kotlinc = shutil.which("kotlinc")
    if not kotlinc:
        pytest.skip("kotlinc not available — skipping Kotlin syntax gate")
    proc = subprocess.run(
        [kotlinc, str(kt_file), "-d", str(kt_file.parent / "_out")],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return
    syntax_errs = [
        line
        for line in proc.stderr.splitlines()
        if "error:" in line and any(m in line.lower() for m in _KOTLINC_SYNTAX_MARKERS)
    ]
    assert not syntax_errs, "Generated Kotlin has syntax errors:\n" + "\n".join(syntax_errs)


def _js_syntax_ok(js_file: Path) -> None:
    """Assert generated JavaScript parses. node --check is syntax-only, so it
    needs none of the WebdriverIO/Mocha globals at runtime."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available — skipping JS syntax gate")
    proc = subprocess.run([node, "--check", str(js_file)], capture_output=True, text=True)
    assert proc.returncode == 0, "Generated JS has syntax errors:\n" + proc.stderr


def _check_golden(rel_path: str, content: str) -> None:
    golden = GOLDEN_DIR / rel_path
    # Always UTF-8 / LF: golden files contain non-ASCII (em dash) and the
    # emitter produces LF. On Windows the default text encoding is cp1252 and
    # write would translate newlines, both of which break the comparison.
    if os.environ.get("UPDATE_GOLDENS"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(content, encoding="utf-8", newline="\n")
        return
    assert golden.exists(), f"Missing golden file: {golden} (run with UPDATE_GOLDENS=1)"
    assert content == golden.read_text(encoding="utf-8"), (
        f"Output drifted from golden {rel_path}. " f"If intentional, regenerate with UPDATE_GOLDENS=1."
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
        f.write_text(content, encoding="utf-8", newline="\n")
        if path.endswith(".py"):
            py_compile.compile(str(f), doraise=True)
            checked += 1
        elif path.endswith(".java"):
            _java_syntax_ok(f)
            checked += 1
        elif path.endswith(".js"):
            _js_syntax_ok(f)
            checked += 1
        elif path.endswith(".kt"):
            _kotlin_syntax_ok(f)
            checked += 1
    assert checked, f"{target_id} produced no source to validate"


def test_python_pytest_uses_condition_based_waits(login_model: TestModel):
    """P3: the flagship Python target must synchronise with condition-based waits
    (WebDriverWait), never a global implicit wait or a fixed sleep — the classic
    flakiness anti-patterns a recorder is prone to emitting."""
    out = get_emitter("python_pytest").emit(login_model)
    src = "\n".join(out.values())
    assert "WebDriverWait" in src
    assert "implicitly_wait" not in src
    assert "time.sleep" not in src


@pytest.mark.parametrize("target_id", ["js_webdriverio", "js_cucumber"])
def test_js_targets_use_condition_based_waits(target_id: str, login_model: TestModel):
    """P3: the JavaScript/WebdriverIO targets must synchronise with a condition
    (waitUntil), never a fixed driver.pause() — the flakiness anti-pattern."""
    src = "\n".join(get_emitter(target_id).emit(login_model).values())
    assert "waitUntil" in src
    assert "driver.pause" not in src


@pytest.mark.parametrize("target_id", TARGET_IDS)
def test_no_fixed_wait_anti_patterns(target_id: str, login_model: TestModel):
    """P3: no target may emit a fixed sleep or a global implicit wait — the two
    canonical flakiness anti-patterns. Synchronisation must be condition-based."""
    src = "\n".join(get_emitter(target_id).emit(login_model).values())
    for anti in ("implicitlyWait", "implicitly_wait", "Thread.sleep", "time.sleep", "driver.pause"):
        assert anti not in src, f"{target_id} emits the {anti!r} anti-pattern"


def test_python_pytest_isolates_test_data_and_state(login_model: TestModel):
    """P8: input data lives in a TEST_DATA table (not inline send_keys literals) so
    it changes in one place, and each test runs on a reset app (isolated,
    parallel-safe)."""
    src = "\n".join(get_emitter("python_pytest").emit(login_model).values())
    assert "TEST_DATA = {" in src
    assert "send_keys(TEST_DATA[" in src  # references the table
    assert 'noReset", False' in src  # fresh app state per test


@pytest.mark.parametrize(
    "toolkit,needle",
    [("native", None), ("compose", "Jetpack Compose"), ("flutter", "Flutter"), ("hybrid", "WebView")],
)
def test_python_pytest_surfaces_toolkit_locator_guidance(toolkit, needle, login_model: TestModel):
    """P11: Compose/Flutter/WebView apps locate differently — the generated file
    tells the tester how; a native app carries no such note."""
    login_model.toolkit = toolkit
    src = "\n".join(get_emitter("python_pytest").emit(login_model).values())
    if needle is None:
        assert "UI toolkit:" not in src
    else:
        assert needle in src and "UI toolkit:" in src


def test_ios_launch_args_carried_into_generated_setup(login_model: TestModel):
    """P9: the launch arguments the crawl used (e.g. to skip a login gate) are
    emitted into the driver setup, so generated tests start in the same state."""
    login_model.platform = Platform.IOS
    login_model.launch_args = ["-StartUnlocked", "1"]
    src = "\n".join(get_emitter("python_pytest").emit(login_model).values())
    assert "processArguments" in src and '"-StartUnlocked", "1"' in src


def test_kotlin_appium_ios_emits_ios_driver(login_model: TestModel):
    """Fix 1: the kotlin_appium template was hardwired to Android. An iOS model
    must import/use IOSDriver + XCUITestOptions, never the Android types."""
    login_model.platform = Platform.IOS
    src = "\n".join(get_emitter("kotlin_appium").emit(login_model).values())
    assert "IOSDriver" in src and "XCUITestOptions" in src
    assert "AndroidDriver" not in src
    assert "UiAutomator2Options" not in src


_IMPERATIVE_TARGETS = ["python_pytest", "java_testng", "kotlin_appium", "js_webdriverio"]
_BDD_TARGETS = ["python_pytest_bdd", "java_cucumber", "js_cucumber"]


@pytest.mark.parametrize("target_id", _IMPERATIVE_TARGETS)
def test_swipe_rendered_in_every_imperative_target(target_id: str, login_model: TestModel):
    """Fix 2: SWIPE used to silently vanish (no template branch). The fixture now
    contains a swipe; every imperative target must actually render it."""
    src = "\n".join(get_emitter(target_id).emit(login_model).values())
    assert "swipeGesture" in src  # Android W3C-style swipe emitted, step not dropped


@pytest.mark.parametrize("target_id", _BDD_TARGETS)
def test_swipe_does_not_crash_bdd_emitters(target_id: str, login_model: TestModel):
    """Fix 2: phrase() had no SWIPE case, so every BDD emitter raised ValueError on
    a model containing a swipe. It must now render the step instead of crashing."""
    out = get_emitter(target_id).emit(login_model)  # must not raise
    src = "\n".join(out.values())
    assert "I swipe" in src  # present in both the .feature and the step definition


def _ios_gesture_model() -> TestModel:
    from framework.codegen.ir import ActionType, Selector, SelectorStrategy, Step, TestCase

    return TestModel(
        name="Gestures",
        app_package="com.example.app",
        platform=Platform.IOS,
        cases=[
            TestCase(
                name="gestures",
                steps=[
                    # Non-TEXT selectors: this test targets the gesture-emission fix,
                    # not the separate TEXT->uiautomator locator mapping (out of scope).
                    Step(ActionType.SCROLL_TO, selector=Selector(SelectorStrategy.ACCESSIBILITY_ID, "settings_row")),
                    Step(ActionType.LONG_PRESS, selector=Selector(SelectorStrategy.ACCESSIBILITY_ID, "row")),
                    Step(ActionType.PRESS_KEY, text="ENTER"),
                    Step(ActionType.SWIPE, direction="left"),
                ],
            )
        ],
    )


@pytest.mark.parametrize("target_id", _IMPERATIVE_TARGETS)
def test_ios_gestures_avoid_android_only_calls(target_id: str):
    """Fix 3: iOS models used to emit Android-only gestures (androidUIAutomator
    scrollIntoView, mobile: longClickGesture, pressKeyCode / AndroidDriver casts),
    which throw on a real iOS run. None of those may appear for an iOS model."""
    src = "\n".join(get_emitter(target_id).emit(_ios_gesture_model()).values())
    for android_only in (
        "ANDROID_UIAUTOMATOR",
        "androidUIAutomator",
        "longClickGesture",
        "pressKeyCode",
        "press_keycode",
        "AndroidKey",
        "AndroidDriver",
    ):
        assert android_only not in src, f"{target_id} still emits Android-only {android_only!r} for iOS"
    # And the iOS equivalents are present.
    assert "mobile: scroll" in src
    assert "mobile: swipe" in src


@pytest.mark.parametrize("target_id", _BDD_TARGETS)
def test_ios_bdd_step_defs_avoid_android_only_calls(target_id: str):
    """Fix 3, BDD flavour: the generic step-definition libraries must also gate
    their Android-only gestures behind the platform for an iOS model."""
    src = "\n".join(get_emitter(target_id).emit(_ios_gesture_model()).values())
    for android_only in ("ANDROID_UIAUTOMATOR", "androidUIAutomator", "longClickGesture", "pressKeyCode", "AndroidKey"):
        assert android_only not in src, f"{target_id} still emits Android-only {android_only!r} for iOS"


def test_ir_roundtrip(login_model: TestModel):
    """IR must survive a JSON round-trip so fixtures stay portable."""
    restored = TestModel.from_dict(login_model.to_dict())
    assert restored.to_dict() == login_model.to_dict()


def test_espresso_annotates_unsupported_xpath():
    """Espresso has no XPath locator. A step whose primary selector is XPath
    must be honestly annotated as skipped, not silently emit broken code."""
    from framework.codegen.ir import (
        ActionType,
        Selector,
        SelectorStrategy,
        Step,
        TestCase,
        TestModel as TM,
    )

    model = TM(
        name="XpathOnly",
        app_package="com.example.app",
        cases=[
            TestCase(
                name="tap_xpath",
                steps=[
                    Step(
                        ActionType.TAP,
                        selector=Selector(SelectorStrategy.XPATH, "//button[1]"),
                    )
                ],
            )
        ],
    )
    out = get_emitter("kotlin_espresso").emit(model)
    code = next(iter(out.values()))
    assert "SKIPPED — Espresso has no XPath" in code
    assert "onView(" not in code  # no broken locator emitted
