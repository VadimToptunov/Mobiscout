"""One suite for both platforms: the Android and the iOS crawl of the same app merged into one
kit whose pages carry a locator per platform. The SAME generated kit is executed twice — with
MOBISCOUT_PLATFORM=android against the Android app and =ios against the iOS app — green on both,
red when either breaks; what only one platform does (Back) runs there and is skipped, with the
reason, on the other."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from framework.codegen.bdd_model import build_bdd_model
from framework.codegen.cross_platform import merge_platform_models
from framework.codegen.framework_bdd_python import render_behave, render_pytest_bdd
from framework.codegen.framework_model import build_framework_model
from framework.codegen.framework_python import render_python
from framework.crawler.to_codegen import build_test_model
from tests.codegen.test_kit_execution import (
    _CONFTEST,
    _fake_app,
    _ios_login_catalog,
    _run_pytest,
    _run_python_bdd,
    _shared_chrome,
)

_APPS = {"android": ("com.x", ".Main"), "ios": ("com.x.ios", None)}


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def _crawls():
    android = _shared_chrome()
    android.back_returns = [("catalog", "home")]  # Back was seen to work — on Android only
    return {"android": android, "ios": _ios_login_catalog()}


def _merged():
    models = {}
    for platform, result in _crawls().items():
        app_id, activity = _APPS[platform]
        model = build_test_model(result, app_package=app_id, app_activity=activity)
        models[platform] = build_framework_model(result, model, app_id)
    return merge_platform_models(models)


def _fake(platform, broken=False):
    result = _crawls()[platform]
    app = _fake_app(result, "" if platform == "ios" else "com.x")
    # iOS has no system Back: if a kit ran its Android-only Back test there, it would FAIL — so
    # a green iOS run proves the test was skipped, not merely that it happened to pass.
    app["back_works"] = platform != "ios"
    if broken:
        app["transitions"] = []
    return app


def _write(files, root):
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    conftest = root / "conftest.py"
    if conftest.exists():  # the device-free Appium in front of the kit's own fixtures
        conftest.write_text(
            _CONFTEST.read_text(encoding="utf-8") + "\n\n" + conftest.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return root


def test_pages_and_elements_align_across_platforms_with_a_locator_each():
    fm = _merged()
    assert list(fm.apps) == ["android", "ios"] and fm.apps["ios"].app_id == "com.x.ios"
    home = fm.page("Home")
    sign_in = home.element("sign_in")
    assert set(sign_in.selectors) == {"android", "ios"}
    assert sign_in.selectors["android"].value != sign_in.selectors["ios"].value
    assert set(home.identities) == {"android", "ios"}


def test_what_both_platforms_do_runs_on_both_and_back_only_on_android():
    fm = _merged()
    back = [sc for sc in fm.scenarios if any(c.op == "back" for c in sc.calls)]
    assert back and all(sc.platforms == ["android"] for sc in back), [(s.name, s.platforms) for s in back]
    shared = [sc for sc in fm.scenarios if sc.platforms is None]
    assert shared, "the scenarios both crawls produced must run on both platforms"


def test_the_kit_picks_its_platform_at_run_time():
    files = render_python(_merged())
    base, conftest = files["pages/base_page.py"], files["conftest.py"]
    assert 'PLATFORM = os.environ.get("MOBISCOUT_PLATFORM", "android").lower()' in base
    assert '"android": "com.x"' in base and '"ios": "com.x.ios"' in base
    assert 'if PLATFORM == "ios":' in conftest and "XCUITestOptions" in conftest and "UiAutomator2Options" in conftest
    page = files["pages/home_page.py"]
    assert page.count('"android":') >= 3 and page.count('"ios":') >= 3, page
    tests = "\n".join(c for p, c in files.items() if p.startswith("tests/test_"))
    assert "@pytest.mark.android\ndef test_back_from" in tests, tests


def test_bdd_features_tag_what_only_one_platform_does():
    bm = build_bdd_model(_merged())
    tagged = [sc for f in bm.features for sc in f.scenarios if "android" in sc.tags]
    assert tagged and all(any(s.step.op == "back" for s in sc.steps) for sc in tagged)


@pytest.mark.parametrize("platform", ["android", "ios"])
def test_one_pytest_kit_runs_green_on_each_platform_and_red_when_it_breaks(platform, tmp_path, monkeypatch):
    kit = _write(render_python(_merged()), tmp_path / "kit")
    monkeypatch.setenv("MOBISCOUT_PLATFORM", platform)
    healthy = _run_pytest(kit, _fake(platform), verbose=True)
    assert healthy.returncode == 0, f"{platform}:\n{healthy.stdout}\n{healthy.stderr}"
    back = [ln for ln in healthy.stdout.splitlines() if "test_back_from" in ln]
    assert back and all(("PASSED" if platform == "android" else "SKIPPED") in ln for ln in back), healthy.stdout
    broken = _run_pytest(kit, _fake(platform, broken=True), verbose=True)
    assert broken.returncode != 0, f"{platform} passed with navigation broken:\n{broken.stdout}"


@pytest.mark.parametrize("flavour", ["pytest_bdd", "behave"])
@pytest.mark.parametrize("platform", ["android", "ios"])
def test_one_bdd_kit_runs_green_on_each_platform(flavour, platform, tmp_path, monkeypatch):
    pytest.importorskip("behave" if flavour == "behave" else "pytest_bdd")
    render = render_behave if flavour == "behave" else render_pytest_bdd
    kit = _write(render(_merged()), tmp_path / flavour)
    monkeypatch.setenv("MOBISCOUT_PLATFORM", platform)
    proc = _run_python_bdd(kit, _fake(platform), flavour)
    assert proc.returncode == 0, f"{flavour} on {platform}:\n{proc.stdout}\n{proc.stderr}"
    broken = _run_python_bdd(kit, _fake(platform, broken=True), flavour)
    assert broken.returncode != 0, f"{flavour} on {platform} passed with navigation broken:\n{broken.stdout}"


# --- the other languages: the same one-kit-both-platforms contract ---------------------------


def _js_fake(platform, broken=False):
    from tests.codegen.test_framework_js import _fake_app as js_fake_app

    app = js_fake_app(_crawls()[platform], "" if platform == "ios" else "com.x")
    app["backWorks"] = platform != "ios"  # see _fake
    if broken:
        app["transitions"] = []
    return app


@pytest.mark.parametrize("flavour", ["mocha", "cucumber"])
@pytest.mark.parametrize("platform", ["android", "ios"])
def test_one_webdriverio_kit_runs_green_on_each_platform(flavour, platform, tmp_path, monkeypatch):
    from framework.codegen.framework_bdd_js import render_js_cucumber
    from framework.codegen.framework_js import render_js
    from tests.codegen import test_framework_bdd_js, test_framework_js

    if test_framework_js._NODE is None:
        pytest.skip("node not available")
    render, run = (
        (render_js, test_framework_js._run)
        if flavour == "mocha"
        else (
            render_js_cucumber,
            test_framework_bdd_js._run,
        )
    )
    kit = tmp_path / flavour
    test_framework_js._write(kit, render(_merged()))
    monkeypatch.setenv("MOBISCOUT_PLATFORM", platform)
    healthy = run(kit, _js_fake(platform))
    assert healthy.returncode == 0, f"{flavour} on {platform}:\n{healthy.stdout}\n{healthy.stderr}"
    assert ("SKIP:" in healthy.stdout) == (platform == "ios"), healthy.stdout  # Back: Android only
    broken = run(kit, _js_fake(platform, broken=True))
    assert broken.returncode != 0, f"{flavour} on {platform} passed with navigation broken:\n{broken.stdout}"


@pytest.mark.skipif(not os.environ.get("MOBISCOUT_REAL_COMPILE"), reason="needs Maven/Gradle/.NET + network")
@pytest.mark.parametrize(
    "target", ["java_testng", "java_cucumber", "kotlin_appium", "kotlin_cucumber", "csharp_nunit", "csharp_reqnroll"]
)
def test_one_jvm_or_dotnet_kit_runs_green_on_each_platform(target, tmp_path):
    from framework.crawler import page_kit
    from tests.codegen.test_jvm_dotnet_execution import _RUNNERS, _tool

    sys.path.insert(0, str(Path(__file__).parent.parent / "support"))
    from fake_appium_server import FakeAppiumServer

    name, args = _RUNNERS[target]
    tool = _tool(name)
    if tool is None:
        pytest.skip(f"{name} not installed")
    render = {**page_kit._TARGET_FRAMEWORKS, **page_kit.FRAMEWORK_ONLY_TARGETS}[target]
    kit = tmp_path / target
    for rel, content in render(_merged()).items():
        path = kit / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for platform, broken in (("android", False), ("ios", False), ("ios", True)):
        with FakeAppiumServer(_fake(platform, broken)) as server:
            env = {**os.environ, "MOBISCOUT_APPIUM_SERVER": server.url, "MOBISCOUT_PLATFORM": platform}
            proc = subprocess.run([tool, *args], cwd=kit, capture_output=True, text=True, timeout=900, env=env)
            assert not server.unknown, server.unknown
        out = (proc.stdout + proc.stderr)[-5000:]
        if broken:
            assert proc.returncode != 0, f"{target} on {platform} passed with navigation broken:\n{out}"
        else:
            assert proc.returncode == 0, f"{target} failed on a healthy {platform} app:\n{out}"
