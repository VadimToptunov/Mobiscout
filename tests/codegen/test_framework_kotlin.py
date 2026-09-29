"""Kotlin (JUnit 5) Page-Object framework: the senior-level contract as automated gates, plus a
REAL compile of the generated Gradle project against Appium java-client + Selenium + JUnit.

The real compile runs ``gradle compileTestKotlin`` on the kit's own build.gradle.kts, so it
proves the build file resolves as well as the sources compiling. It needs Gradle and network
access, so it runs where ``MOBISCOUT_REAL_COMPILE=1`` (the CI codegen job) is set."""

import os
import re
import shutil
import subprocess

import pytest

from framework.codegen.framework_kotlin import render_kotlin
from framework.codegen.framework_model import build_framework_model
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import build_test_model

_SRC = "src/test/kotlin/mobiscout"


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


def _kit(platform):
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
    model = build_test_model(res, app_package="com.x", app_activity=None if ios else ".Main")
    return render_kotlin(build_framework_model(res, model, "com.x"))


def _tests(files):
    return {p: c for p, c in files.items() if p.startswith(f"{_SRC}/tests/")}


def _pages(files):
    return {p: c for p, c in files.items() if p.startswith(f"{_SRC}/pages/") and not p.endswith("/BasePage.kt")}


def test_gradle_layout_with_session_base_page_pages_and_tests(platform):
    files = _kit(platform)
    for required in (
        "build.gradle.kts",
        "settings.gradle.kts",
        f"{_SRC}/support/Session.kt",
        f"{_SRC}/support/BaseTest.kt",
        f"{_SRC}/pages/BasePage.kt",
    ):
        assert required in files, sorted(files)
    assert _pages(files) and _tests(files), sorted(files)


def test_tests_drive_intention_methods_not_raw_elements(platform):
    for path, source in _tests(_kit(platform)).items():
        assert ": BaseTest()" in source, path
        for smell in ("AppiumBy", "findElement", ".click()", ".sendKeys(", "WebDriverWait", "Thread.sleep"):
            assert smell not in source, f"{smell!r} leaked into {path}:\n{source}"


def test_tests_are_named_as_sentences(platform):
    tests = "\n".join(_tests(_kit(platform)).values())
    assert re.search(r"fun `[A-Z][\w ,'()-]+`\(\)", tests), tests


def test_plumbing_lives_only_in_the_base_page(platform):
    for path, source in _pages(_kit(platform)).items():
        assert ": BasePage(driver)" in source, path
        for plumbing in ("WebDriverWait", "findElement", "Thread.sleep", "scrollGesture"):
            assert plumbing not in source, f"{plumbing!r} duplicated in {path}"


def test_no_fixed_sleeps_anywhere(platform):
    for path, source in _kit(platform).items():
        assert "Thread.sleep" not in source and not re.search(r"\b(sleep|delay)\(", source), path


def test_navigating_tap_returns_the_next_typed_page(platform):
    files = _kit(platform)
    page = files[f"{_SRC}/pages/WelcomeBackPage.kt"]
    assert "fun tapSignIn(): CatalogPage {" in page and "return CatalogPage(driver)" in page, page
    tests = "\n".join(_tests(files).values())
    assert "val catalogPage = welcomeBackPage.tapSignIn()" in tests, tests


def test_negative_case_does_not_claim_it_navigated(platform):
    tests = "\n".join(_tests(_kit(platform)).values())
    body = next(chunk for chunk in tests.split("@Test") if "invalid" in chunk.split("\n", 2)[1].lower())
    assert "= welcomeBackPage.tapSignIn()" not in body and "welcomeBackPage.tapSignIn()" in body, body


def test_one_appium_session_per_run_with_an_app_restart_per_test(platform):
    files = _kit(platform)
    session, base = files[f"{_SRC}/support/Session.kt"], files[f"{_SRC}/support/BaseTest.kt"]
    assert "object Session" in session and "addShutdownHook" in session
    # A crashed session is dropped and reopened before the next test, not reused dead.
    assert "fun ensureAlive()" in session and "queryAppState(APP)" in session
    assert "Session.ensureAlive()" in base
    assert ("val driver: IOSDriver" if platform == "ios" else "val driver: AndroidDriver") in session
    assert "waitForIdleTimeout" in session and "setNoReset(true)" in session
    assert "@BeforeEach" in base and "terminateApp(Session.APP)" in base and "activateApp(Session.APP)" in base


def test_build_pins_selenium_and_includes_the_junit_launcher(platform):
    build = _kit(platform)["build.gradle.kts"]
    assert "selenium-bom" in build and "io.appium:java-client" in build
    # Gradle 9 no longer puts the JUnit Platform launcher on the test runtime implicitly.
    assert "junit-platform-launcher" in build and "useJUnitPlatform()" in build


@pytest.mark.skipif(
    not (os.environ.get("MOBISCOUT_REAL_COMPILE") and shutil.which("gradle")),
    reason="real compile needs Gradle + network (set MOBISCOUT_REAL_COMPILE=1)",
)
def test_kit_compiles_against_real_appium_selenium_and_junit(platform, tmp_path):
    for rel, content in _kit(platform).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    gradle = shutil.which("gradle")
    assert gradle is not None
    proc = subprocess.run(
        [gradle, "-q", "--no-daemon", "compileTestKotlin"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert proc.returncode == 0, f"generated Kotlin kit does not compile:\n{proc.stdout}\n{proc.stderr}"
