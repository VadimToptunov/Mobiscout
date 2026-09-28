"""Flat JVM kits must compile against their REAL dependencies, not just parse.

The javac/kotlinc gate in test_emitters forgives "cannot find symbol" (it has no jars), which
hid two shipped defects: every flat Java kit called ``driver.activateApp(...)`` on a field typed
``AppiumDriver`` — that method lives on ``InteractsWithApps`` (AndroidDriver / IOSDriver), so the
kit never compiled — and the scaffold pinned java-client 9.3.0, which no longer compiles against
the Selenium Maven resolves today. The always-on tests pin both fixes; the real compile runs where
``MOBISCOUT_REAL_COMPILE=1`` (the CI codegen job) and Maven are available."""

import os
import shutil
import subprocess

import pytest

from framework.codegen import get_emitter
from framework.codegen.scaffold import APPIUM_JAVA_CLIENT_VERSION, SELENIUM_VERSION, scaffold_files
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import build_test_model


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def _el(cls, text="", rid="", desc="", clk=True, platform="android"):
    ios = platform == "ios"
    return CrawlElement(
        # iOS carries the accessibility identifier in resource_id; Android an app-scoped id.
        resource_id=(rid if ios else f"com.x:id/{rid}") if rid else "",
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=clk,
        bounds=(0, 0, 300, 60),
        package="" if ios else "com.x",
    )


def _model(platform="android"):
    ios = platform == "ios"
    text, field, button = (
        ("StaticText", "TextField", "Button")
        if ios
        else (
            "android.widget.TextView",
            "android.widget.EditText",
            "android.widget.Button",
        )
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
        [
            _el(text, "Catalog", clk=False, platform=platform),
            _el(button, "Product", rid="prod", platform=platform),
        ],
        platform=platform,
    )
    res = CrawlResult(screens={"login": login, "catalog": catalog})
    res.transitions = [("login", _el(button, "Sign in", rid="signin", platform=platform), "catalog")]
    return build_test_model(res, app_package="com.x", app_activity=None if ios else ".Main")


@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("target", ["java_testng", "java_cucumber"])
def test_flat_java_types_the_driver_as_a_platform_driver(target, platform):
    # activateApp/terminateApp are on AndroidDriver/IOSDriver (InteractsWithApps), not AppiumDriver.
    source = "\n".join(get_emitter(target).emit(_model(platform)).values())
    expected = "IOSDriver" if platform == "ios" else "AndroidDriver"
    assert f"private {expected} driver;" in source, source[:2000]
    assert "private AppiumDriver driver;" not in source


@pytest.mark.parametrize("target", ["java_testng", "java_cucumber", "kotlin_appium"])
def test_scaffold_pins_a_compatible_client_and_selenium(target):
    files = scaffold_files(_model(), target)
    build = files.get("pom.xml") or files.get("build.gradle.kts") or ""
    assert APPIUM_JAVA_CLIENT_VERSION in build and "9.3.0" not in build, build
    assert "selenium-bom" in build and SELENIUM_VERSION in build, build


@pytest.mark.skipif(
    not (os.environ.get("MOBISCOUT_REAL_COMPILE") and shutil.which("mvn")),
    reason="real compile needs Maven + network (set MOBISCOUT_REAL_COMPILE=1)",
)
@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("target", ["java_testng", "java_cucumber"])
def test_flat_java_kit_compiles_against_real_deps(target, platform, tmp_path):
    model = _model(platform)
    for name, content in get_emitter(target).emit(model).items():
        path = tmp_path / target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for rel, content in scaffold_files(model, target).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    mvn = shutil.which("mvn")
    assert mvn is not None
    proc = subprocess.run([mvn, "-q", "-B", "test-compile"], cwd=tmp_path, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, f"{target} kit does not compile:\n{proc.stdout}\n{proc.stderr}"
