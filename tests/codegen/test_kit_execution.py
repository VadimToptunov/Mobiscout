"""Execute an emitted python_pytest kit against a device-free fake Appium and assert it
goes green — the product's core promise ("generated tests pass") turned from a py_compile
guess into an executed check.

The fake app (tests/support/kit_fake_conftest.py) is a screen state-machine built here from
the CrawlResult, independently of the emitter: locators come from `selector_for` + the
emitter's own `by_value` (so model and kit agree on wire strings), while *which screen an
element is on* and *where a tap goes* come from the crawl structure — so a codegen bug that
asserts an element the flow never reached fails for real. A negative control proves the
harness has teeth.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from framework.codegen import get_emitter
from framework.codegen.emitters._python_common import by_value
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import _owned, build_test_model, selector_for

_CONFTEST = Path(__file__).parent.parent / "support" / "kit_fake_conftest.py"


class _AB:
    """AppiumBy wire strings — matches the fake conftest, so evaluating a `by_value`
    tuple literal yields the exact (by, value) the kit resolves to at runtime."""

    ID = "id"
    ACCESSIBILITY_ID = "accessibility id"
    XPATH = "xpath"
    CLASS_NAME = "class name"
    NAME = "name"
    ANDROID_UIAUTOMATOR = "-android uiautomator"
    IOS_PREDICATE = "-ios predicate string"
    IOS_CLASS_CHAIN = "-ios class chain"


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def _el(cls, text="", rid="", desc="", clk=True):
    return CrawlElement(
        resource_id=(f"com.x:id/{rid}" if rid else ""),
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=clk,
        bounds=(0, 0, 300, 60),
        package="com.x",
    )


def _runtime_locator(sel, platform):
    """The exact (by, value) the kit will call find_element with — read off the emitter's
    own `by_value` rendering and interpreted the way Python will at kit runtime."""
    rendered = by_value(sel, platform)  # e.g. '(AppiumBy.ID, "com.x:id/email")'
    by, value = eval(rendered, {"AppiumBy": _AB})  # noqa: S307 - our own rendered literal
    return by, value


def _fake_app(result: CrawlResult, package: str) -> dict:
    fps = list(result.screens)
    idx = {fp: i for i, fp in enumerate(fps)}
    screens = []
    for fp in fps:
        screen = result.screens[fp]
        owned = _owned(screen, package)
        locs = []
        for e in owned:
            sel = selector_for(e, owned, screen.platform)
            if sel is not None:
                by, value = _runtime_locator(sel, screen.platform)
                locs.append([by, value])
        screens.append(locs)
    transitions = []
    for from_fp, element, to_fp in result.transitions:
        if from_fp not in idx or to_fp not in idx:
            continue
        owned = _owned(result.screens[from_fp], package)
        sel = selector_for(element, owned, result.screens[from_fp].platform)
        if sel is None:
            continue
        by, value = _runtime_locator(sel, result.screens[from_fp].platform)
        transitions.append([idx[from_fp], by, value, idx[to_fp]])
    return {"start": 0, "screens": screens, "transitions": transitions}


def _shop() -> CrawlResult:
    login = CrawlScreen(
        "login",
        [
            _el("android.widget.TextView", "Welcome back", clk=False),
            _el("android.widget.EditText", rid="email", desc="Email"),
            _el("android.widget.EditText", rid="password", desc="Password"),
            _el("android.widget.Button", "Sign in", rid="signin"),
        ],
        platform="android",
    )
    home = CrawlScreen(
        "home",
        [
            _el("android.widget.TextView", "Catalog", clk=False),
            _el("android.widget.EditText", rid="search", desc="Search"),
            _el("android.widget.Button", "Product", rid="prod"),
        ],
        platform="android",
    )
    res = CrawlResult(screens={"login": login, "home": home})
    res.transitions = [("login", _el("android.widget.Button", "Sign in", rid="signin"), "home")]
    return res


def _emit_kit(result: CrawlResult, tmp: Path, fuzz: bool = False) -> Path:
    model = build_test_model(result, app_package="com.x", app_activity=".Main", fuzz=fuzz)
    kit = tmp / "kit"
    kit.mkdir()
    for name, content in get_emitter("python_pytest").emit(model).items():
        (kit / name).write_text(content, encoding="utf-8")
    shutil.copy(_CONFTEST, kit / "conftest.py")
    return kit


def _run_pytest(kit: Path, model: dict) -> subprocess.CompletedProcess:
    model_file = kit / "_fake_app.json"
    model_file.write_text(json.dumps(model), encoding="utf-8")
    # Run the emitted kit in a CLEAN pytest environment. Inheriting the outer run's
    # PYTEST_ADDOPTS and pytest-cov subprocess vars (COV_CORE_*/COVERAGE_*) makes the child
    # pytest try to load the parent's config / coverage data file — a temp path the parent
    # may already have cleaned, which crashes the child at collection (a Windows-CI flake).
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("PYTEST_", "COV_")) and k not in ("COVERAGE_FILE", "COVERAGE_PROCESS_START")
    }
    env["MOBISCOUT_FAKE_APP"] = str(model_file)
    env["MOBISCOUT_APPIUM_SERVER"] = "http://fake"
    return subprocess.run(
        # --basetemp under the kit keeps the child's temp isolated from the parent's, so a
        # cleaned parent tmp can't be referenced during the child's collection.
        [
            sys.executable,
            "-m",
            "pytest",
            str(kit),
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(kit / ".pytest_tmp"),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_emitted_kit_runs_green_against_fake_app(tmp_path):
    result = _shop()
    kit = _emit_kit(result, tmp_path)
    proc = _run_pytest(kit, _fake_app(result, "com.x"))
    assert proc.returncode == 0, f"kit did not pass:\n{proc.stdout}\n{proc.stderr}"
    assert "passed" in proc.stdout


def test_find_scrolls_to_reach_a_below_fold_element(tmp_path):
    # Move a start-screen element below the fold: present only after a scroll. The kit
    # must still pass, which it can only do if the generated _find scrolls on miss.
    result = _shop()
    kit = _emit_kit(result, tmp_path)
    model = _fake_app(result, "com.x")
    hidden = model["screens"][0].pop()  # a login-screen locator [by, value]
    model.setdefault("reveals", []).append([0, hidden[0], hidden[1]])
    proc = _run_pytest(kit, model)
    assert proc.returncode == 0, f"_find did not scroll to the below-fold element:\n{proc.stdout}\n{proc.stderr}"


def test_fuzz_kit_runs_green_against_fake_app(tmp_path):
    # Opt-in fuzz tests (adversarial inputs → assert the form doesn't advance) must be
    # valid, runnable code that passes against an app whose form validation rejects them.
    result = _shop()
    kit = _emit_kit(result, tmp_path, fuzz=True)
    assert any("fuzz_" in p.name or "fuzz_" in p.read_text() for p in kit.glob("*.py"))
    proc = _run_pytest(kit, _fake_app(result, "com.x"))
    assert proc.returncode == 0, f"fuzz kit did not pass:\n{proc.stdout}\n{proc.stderr}"


def test_harness_has_teeth_broken_navigation_fails(tmp_path):
    # Drop the login->home transition: the journey tests can no longer reach the home
    # screen, so the emitted kit must FAIL. Proves the green above isn't vacuous.
    result = _shop()
    kit = _emit_kit(result, tmp_path)
    broken = _fake_app(result, "com.x")
    broken["transitions"] = []
    proc = _run_pytest(kit, broken)
    assert proc.returncode != 0, f"broken navigation should fail the kit but passed:\n{proc.stdout}"
