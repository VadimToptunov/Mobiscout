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


def _emit_kit(result: CrawlResult, tmp: Path) -> Path:
    model = build_test_model(result, app_package="com.x", app_activity=".Main")
    kit = tmp / "kit"
    kit.mkdir()
    for name, content in get_emitter("python_pytest").emit(model).items():
        (kit / name).write_text(content, encoding="utf-8")
    shutil.copy(_CONFTEST, kit / "conftest.py")
    return kit


def _run_pytest(kit: Path, model: dict) -> subprocess.CompletedProcess:
    model_file = kit / "_fake_app.json"
    model_file.write_text(json.dumps(model), encoding="utf-8")
    env = {**os.environ, "MOBISCOUT_FAKE_APP": str(model_file), "MOBISCOUT_APPIUM_SERVER": "http://fake"}
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(kit), "-q", "-p", "no:cacheprovider"],
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


def test_harness_has_teeth_broken_navigation_fails(tmp_path):
    # Drop the login->home transition: the journey tests can no longer reach the home
    # screen, so the emitted kit must FAIL. Proves the green above isn't vacuous.
    result = _shop()
    kit = _emit_kit(result, tmp_path)
    broken = _fake_app(result, "com.x")
    broken["transitions"] = []
    proc = _run_pytest(kit, broken)
    assert proc.returncode != 0, f"broken navigation should fail the kit but passed:\n{proc.stdout}"
