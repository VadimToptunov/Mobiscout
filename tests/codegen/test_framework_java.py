"""Java (TestNG) Page-Object framework: the senior-level contract as automated gates, plus a
REAL compile against Appium java-client + Selenium + TestNG.

The older Java gate is syntax-only (javac without the jars, "cannot find symbol" forgiven),
which can't see a wrong driver method or an incompatible dependency. The real-compile test
here resolves the kit's own pom.xml and runs ``mvn test-compile`` — it is what caught
java-client 9.3.0 breaking against the Selenium that Maven resolves today. It needs Maven and
network access, so it runs where ``MOBISCOUT_REAL_COMPILE=1`` (the CI codegen job) is set."""

import os
import re
import shutil
import subprocess

import pytest

from framework.codegen.framework_java import render_java
from framework.codegen.framework_model import build_framework_model
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import build_test_model

_SRC = "src/test/java/mobiscout"


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


def _result(platform="android") -> CrawlResult:
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


@pytest.fixture(params=["android", "ios"])
def platform(request):
    """Every gate runs for both platforms — one suite, two drivers."""
    return request.param


def _kit(platform="android"):
    res = _result(platform)
    model = build_test_model(res, app_package="com.x", app_activity=None if platform == "ios" else ".Main")
    return render_java(build_framework_model(res, model, "com.x"))


def _tests(files):
    return {p: c for p, c in files.items() if p.startswith(f"{_SRC}/tests/")}


def _pages(files):
    return {p: c for p, c in files.items() if p.startswith(f"{_SRC}/pages/") and not p.endswith("/BasePage.java")}


def test_maven_layout_with_base_page_base_test_pages_and_tests(platform):
    files = _kit(platform)
    for required in ("pom.xml", "testng.xml", f"{_SRC}/pages/BasePage.java", f"{_SRC}/support/BaseTest.java"):
        assert required in files, sorted(files)
    assert _pages(files) and _tests(files), sorted(files)


def test_tests_drive_intention_methods_not_raw_elements(platform):
    for path, source in _tests(_kit(platform)).items():
        assert "extends BaseTest" in source, path
        for smell in ("AppiumBy", "findElement", ".click()", ".sendKeys(", "WebDriverWait", "Thread.sleep"):
            assert smell not in source, f"{smell!r} leaked into {path}:\n{source}"


def test_plumbing_lives_only_in_the_base_page(platform):
    for path, source in _pages(_kit(platform)).items():
        assert "extends BasePage" in source, path
        for plumbing in ("WebDriverWait", "findElement", "Thread.sleep", "scrollGesture"):
            assert plumbing not in source, f"{plumbing!r} duplicated in {path}"


def test_no_fixed_sleeps_anywhere(platform):
    for path, source in _kit(platform).items():
        assert "Thread.sleep" not in source and not re.search(r"\bsleep\(", source), path


def test_navigating_tap_returns_the_next_typed_page(platform):
    files = _kit(platform)
    page = files[f"{_SRC}/pages/WelcomeBackPage.java"]
    assert "public CatalogPage tapSignIn()" in page and "return new CatalogPage(driver);" in page, page
    tests = "\n".join(_tests(files).values())
    assert "CatalogPage catalogPage = welcomeBackPage.tapSignIn();" in tests, tests


def test_variables_are_camel_case_not_the_class_name(platform):
    for path, source in _tests(_kit(platform)).items():
        assert not re.search(r"\b(\w+Page) \1 =", source), f"variable named like its class in {path}:\n{source}"


def test_negative_case_does_not_claim_it_navigated(platform):
    tests = "\n".join(_tests(_kit(platform)).values())
    body = tests.split("rejectsInvalidInput", 1)[1].split("@Test", 1)[0]
    assert "= welcomeBackPage.tapSignIn();" not in body and "welcomeBackPage.tapSignIn();" in body, body


def test_one_appium_session_per_suite_with_an_app_restart_per_test(platform):
    base = _kit(platform)[f"{_SRC}/support/BaseTest.java"]
    assert (
        "protected static IOSDriver driver;" if platform == "ios" else "protected static AndroidDriver driver;"
    ) in base
    assert "@BeforeSuite" in base and "@AfterSuite" in base
    assert "terminateApp(APP)" in base and "activateApp(APP)" in base
    assert "waitForIdleTimeout" in base


def test_pom_pins_selenium_so_the_build_is_reproducible(platform):
    pom = _kit(platform)["pom.xml"]
    assert "selenium-bom" in pom and "<scope>import</scope>" in pom
    assert "<artifactId>java-client</artifactId>" in pom and "<artifactId>testng</artifactId>" in pom


@pytest.mark.skipif(
    not (os.environ.get("MOBISCOUT_REAL_COMPILE") and shutil.which("mvn")),
    reason="real compile needs Maven + network (set MOBISCOUT_REAL_COMPILE=1)",
)
def test_kit_compiles_against_real_appium_selenium_and_testng(platform, tmp_path):
    for rel, content in _kit(platform).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    mvn = shutil.which("mvn")
    assert mvn is not None
    proc = subprocess.run(
        [mvn, "-q", "-B", "test-compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, f"generated Java kit does not compile:\n{proc.stdout}\n{proc.stderr}"
