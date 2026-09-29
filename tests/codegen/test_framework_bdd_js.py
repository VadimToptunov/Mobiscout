"""WebdriverIO Cucumber suite on the page objects: the BDD contract as gates, and the kit EXECUTED
in a device-free WebdriverIO + Cucumber runtime (tests/support/wdio_cucumber_fake_runner.mjs) —
green on a healthy app, red when a tap goes nowhere or a step has no definition. Both platforms."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from framework.codegen.framework_bdd_js import render_js_cucumber
from framework.codegen.framework_model import build_framework_model
from framework.crawler.to_codegen import build_test_model
from tests.codegen.test_framework_js import _fake_app, _package, _result, _write

_RUNNER = Path(__file__).parent.parent / "support" / "wdio_cucumber_fake_runner.mjs"
_NODE = shutil.which("node")


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


@pytest.fixture(params=["android", "ios"])
def platform(request):
    """Every gate runs for both platforms — one suite, two drivers."""
    return request.param


def _kit(platform):
    res = _result(platform)
    model = build_test_model(res, app_package="com.x", app_activity=None if platform == "ios" else ".Main")
    return res, render_js_cucumber(build_framework_model(res, model, "com.x"))


def _steps(files):
    return {p: c for p, c in files.items() if p.startswith("features/step-definitions/")}


def _run(kit: Path, app: dict) -> subprocess.CompletedProcess:
    app_path = kit / "fake-app.json"
    app_path.write_text(json.dumps(app), encoding="utf-8")
    assert _NODE is not None
    return subprocess.run(
        [_NODE, str(_RUNNER), str(kit)],
        # Inherit the environment: Node aborts on Windows without SystemRoot and friends.
        env={**os.environ, "MOBISCOUT_FAKE_APP": str(app_path)},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_layout_and_cucumber_wiring(platform):
    files = _kit(platform)[1]
    assert "test/pageobjects/base.page.js" in files and _steps(files)
    assert any(p.startswith("features/") and p.endswith(".feature") for p in files)
    assert not any(p.startswith("test/specs/") for p in files)
    assert "@wdio/cucumber-framework" in json.loads(files["package.json"])["devDependencies"]
    conf = files["wdio.conf.js"]
    assert "framework: 'cucumber'" in conf and "./features/**/*.feature" in conf
    assert "beforeScenario" in conf and "terminateApp(APP)" in conf and "activateApp(APP)" in conf


def test_steps_are_calls_on_page_objects(platform):
    for path, source in _steps(_kit(platform)[1]).items():
        assert "'@wdio/cucumber-framework'" in source and "../../test/pageobjects/" in source, path
        for smell in ("$(", "driver.", "pause(", "UiSelector", "XCUIElementType", "setValue", "click()"):
            assert smell not in source, f"{smell!r} in {path}:\n{source}"
        for body in re.findall(r"async \((?:value)?\) => \{\n(.*?)\n\}\);", source, re.S):
            statements = [ln.strip() for ln in body.splitlines() if ln.strip()]
            # One call — or, to reach a screen, its taps then the arrival check.
            assert statements and all("Page." in s for s in statements), body
            assert len(statements) == 1 or statements[-1].startswith("expect("), body


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_every_file_is_valid_javascript(platform, tmp_path):
    _write(tmp_path, _kit(platform)[1])
    assert _NODE is not None
    for path in tmp_path.rglob("*.js"):
        proc = subprocess.run([_NODE, "--check", str(path)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{path}:\n{proc.stderr}"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_kit_runs_green_on_a_healthy_app_and_red_when_a_tap_goes_nowhere(platform, tmp_path):
    result, files = _kit(platform)
    _write(tmp_path, files)
    healthy = _run(tmp_path, _fake_app(result, _package(platform)))
    assert healthy.returncode == 0, f"kit failed against a healthy app:\n{healthy.stdout}\n{healthy.stderr}"
    assert " 0 failed" in healthy.stdout, healthy.stdout
    broken = _fake_app(result, _package(platform))
    broken["transitions"] = []
    proc = _run(tmp_path, broken)
    assert proc.returncode == 1, f"broken navigation should fail the kit:\n{proc.stdout}\n{proc.stderr}"
    assert "FAIL: Catalog screen" in proc.stdout, proc.stdout


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_an_undefined_step_fails_the_run(platform, tmp_path):
    result, files = _kit(platform)
    _write(tmp_path, files)
    feature = next(p for p in tmp_path.glob("features/*.feature"))
    text = feature.read_text(encoding="utf-8")
    feature.write_text(text.replace("Given I am on the", "Given I stand on the", 1), encoding="utf-8")
    proc = _run(tmp_path, _fake_app(result, _package(platform)))
    assert proc.returncode == 1 and "undefined step" in proc.stdout, proc.stdout
