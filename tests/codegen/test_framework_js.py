"""WebdriverIO Page-Object framework: the senior-level contract as automated gates, and the
generated specs EXECUTED in a device-free WebdriverIO runtime (tests/support/wdio_fake_runner.mjs)
— green against a healthy app, red when a tap goes nowhere. Both platforms."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from framework.codegen.emitters._js_common import _wdio_selector
from framework.codegen.framework_js import render_js
from framework.codegen.framework_model import build_framework_model
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import _owned, build_test_model, selector_for

_RUNNER = Path(__file__).parent.parent / "support" / "wdio_fake_runner.mjs"
_NODE = shutil.which("node")


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


@pytest.fixture(params=["android", "ios"])
def platform(request):
    """Every gate runs for both platforms — one suite, two drivers."""
    return request.param


def _el(cls, text="", rid="", desc="", clk=True, platform="android"):
    ios = platform == "ios"
    return CrawlElement(
        resource_id=(rid if ios else f"com.x:id/{rid}") if rid else "",
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=clk,
        bounds=(0, 0, 300, 60),
        package="" if ios else "com.x",
    )


def _result(platform) -> CrawlResult:
    ios = platform == "ios"
    text, field, button = (
        ("StaticText", "TextField", "Button")
        if ios
        else ("android.widget.TextView", "android.widget.EditText", "android.widget.Button")
    )
    login = CrawlScreen(
        "login",
        [
            _el(text, "Welcome back", clk=False, platform=platform),
            _el(field, rid="email", desc="Email", platform=platform),
            _el(button, "Sign in", rid="signin", platform=platform),
        ],
        platform=platform,
    )
    catalog = CrawlScreen(
        "catalog",
        [_el(text, "Catalog", clk=False, platform=platform), _el(button, "Product", rid="prod", platform=platform)],
        platform=platform,
    )
    res = CrawlResult(screens={"login": login, "catalog": catalog})
    res.transitions = [("login", _el(button, "Sign in", rid="signin", platform=platform), "catalog")]
    return res


def _kit(platform):
    res = _result(platform)
    model = build_test_model(res, app_package="com.x", app_activity=None if platform == "ios" else ".Main")
    return res, render_js(build_framework_model(res, model, "com.x"))


def _specs(files):
    return {p: c for p, c in files.items() if p.startswith("test/specs/")}


def _pages(files):
    return {p: c for p, c in files.items() if p.startswith("test/pageobjects/") and not p.endswith("base.page.js")}


def _package(platform):
    return "" if platform == "ios" else "com.x"


def _fake_app(result: CrawlResult, package: str) -> dict:
    """The app as the fake runtime sees it: each screen's WebdriverIO selector strings (every
    ranked tier, so fallbacks are reachable) and the transitions between screens."""

    def chain(sel, plat):
        return [_wdio_selector(s, plat) for s in [sel, *sel.fallbacks]]

    fps = list(result.screens)
    idx = {fp: i for i, fp in enumerate(fps)}
    screens = []
    for fp in fps:
        screen = result.screens[fp]
        owned = _owned(screen, package)
        locs: list = []
        for e in owned:
            sel = selector_for(e, owned, screen.platform)
            if sel is not None:
                locs.extend(chain(sel, screen.platform))
        screens.append(locs)
    transitions = []
    for from_fp, element, to_fp in result.transitions:
        screen = result.screens[from_fp]
        sel = selector_for(element, _owned(screen, package), screen.platform)
        if sel is not None:
            transitions.extend([idx[from_fp], s, idx[to_fp]] for s in chain(sel, screen.platform))
    return {"start": 0, "screens": screens, "transitions": transitions}


def _write(root: Path, files: dict) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


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


def test_webdriverio_layout(platform):
    _, files = _kit(platform)
    for required in ("package.json", "wdio.conf.js", "test/pageobjects/base.page.js"):
        assert required in files, sorted(files)
    assert _pages(files) and _specs(files), sorted(files)
    assert json.loads(files["package.json"])["type"] == "module"


def test_specs_drive_intention_methods_not_raw_selectors(platform):
    for path, source in _specs(_kit(platform)[1]).items():
        assert "../pageobjects/" in source, path
        for smell in ("$(", "driver.", "pause(", "'~", "UiSelector", "XCUIElementType", "setValue", "click()"):
            assert smell not in source, f"{smell!r} leaked into {path}:\n{source}"


def test_plumbing_lives_only_in_the_base_page(platform):
    for path, source in _pages(_kit(platform)[1]).items():
        assert "extends BasePage" in source and "export default new " in source, path
        for plumbing in ("waitUntil", "$(", "driver.", "pause("):
            assert plumbing not in source, f"{plumbing!r} duplicated in {path}"


def test_no_fixed_pauses_anywhere(platform):
    for path, source in _kit(platform)[1].items():
        assert not re.search(r"\b(pause|sleep|setTimeout)\(", source), path


def test_navigating_tap_returns_the_next_page(platform):
    page = _kit(platform)[1]["test/pageobjects/welcome-back.page.js"]
    assert "import catalogPage from './catalog.page.js';" in page
    assert re.search(r"async tapSignIn\(\) \{\n\s+await this\._tap\('sign_in'\);\n\s+return catalogPage;", page), page


def test_one_session_per_worker_with_an_app_restart_per_test(platform):
    conf = _kit(platform)[1]["wdio.conf.js"]
    assert "beforeTest" in conf and "terminateApp(APP)" in conf and "activateApp(APP)" in conf
    assert "'appium:noReset': true" in conf and "waitForIdleTimeout" in conf
    assert ("XCUITest" if platform == "ios" else "UiAutomator2") in conf


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
    assert "0 failed" in healthy.stdout, healthy.stdout
    broken = _fake_app(result, _package(platform))
    broken["transitions"] = []
    proc = _run(tmp_path, broken)
    assert proc.returncode == 1, f"broken navigation should fail the kit:\n{proc.stdout}\n{proc.stderr}"
    assert "FAIL: Catalog screen" in proc.stdout, proc.stdout
