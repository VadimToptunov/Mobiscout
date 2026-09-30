"""C# (.NET 10) kits — NUnit page objects and Reqnroll BDD on the same pages: the senior-level
contract as gates for both platforms, plus a REAL ``dotnet build`` against Appium.WebDriver,
NUnit and Reqnroll (Reqnroll's build also generates and compiles the feature bindings).

The build needs the .NET 10 SDK and network access, so it runs where ``MOBISCOUT_REAL_COMPILE=1``
(the CI codegen job); ``DOTNET`` may point at an SDK that is not on PATH."""

import os
import re
import shutil
import subprocess

import pytest

from framework.codegen.framework_csharp import render_csharp, render_reqnroll
from tests.codegen.test_framework_bdd_python import _framework

_RENDERERS = {"nunit": render_csharp, "reqnroll": render_reqnroll}


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


@pytest.fixture(params=["android", "ios"])
def platform(request):
    """Every gate runs for both platforms — one suite, two drivers."""
    return request.param


@pytest.fixture(params=sorted(_RENDERERS))
def flavour(request):
    """NUnit tests and Reqnroll features."""
    return request.param


def _kit(platform, flavour):
    return _RENDERERS[flavour](_framework(platform))


def _pages(files):
    return {p: c for p, c in files.items() if p.startswith("Pages/") and p != "Pages/BasePage.cs"}


def test_layout(platform, flavour):
    files = _kit(platform, flavour)
    for required in ("MobileTests.csproj", "Support/Session.cs", "Pages/BasePage.cs"):
        assert required in files, sorted(files)
    assert _pages(files)
    if flavour == "nunit":
        assert "Support/BaseTest.cs" in files and "SessionLifetime.cs" in files
        assert any(p.startswith("Tests/") for p in files)
    else:
        assert "Support/Hooks.cs" in files and "Reqnroll.NUnit" in files["MobileTests.csproj"]
        assert any(p.startswith("Features/") for p in files) and any(p.startswith("StepDefinitions/") for p in files)


def test_locators_go_through_mobileby_never_selenium_css(platform, flavour):
    # Selenium's By.Id / By.ClassName become CSS selectors under W3C and never match an
    # Appium resource-id or an Android class name.
    for path, source in _pages(_kit(platform, flavour)).items():
        assert "By.Id(" not in source.replace("MobileBy.Id(", "")
        assert "By.ClassName(" not in source.replace("MobileBy.ClassName(", "")


def test_tests_and_steps_drive_page_objects_only(platform, flavour):
    files = _kit(platform, flavour)
    code = {p: c for p, c in files.items() if p.startswith(("Tests/", "StepDefinitions/"))}
    assert code
    for path, source in code.items():
        for smell in ("MobileBy", "FindElement", "Thread.Sleep", "WebDriverWait", "By.XPath"):
            assert smell not in source, f"{smell!r} in {path}"


def test_plumbing_lives_only_in_the_base_page(platform, flavour):
    for path, source in _pages(_kit(platform, flavour)).items():
        assert ": BasePage(driver)" in source, path
        for plumbing in ("WebDriverWait", "FindElement", "Thread.Sleep", "scrollGesture"):
            assert plumbing not in source, f"{plumbing!r} duplicated in {path}"


def test_navigating_tap_returns_the_next_typed_page(platform, flavour):
    page = _kit(platform, flavour)["Pages/WelcomeBackPage.cs"]
    assert "public CatalogPage TapSignIn()" in page and "return new CatalogPage(Driver);" in page, page


def test_one_session_per_run_reopened_if_it_died(platform, flavour):
    session = _kit(platform, flavour)["Support/Session.cs"]
    assert "current ??= Open()" in session and "GetAppState(App)" in session
    assert ("IOSDriver" if platform == "ios" else "AndroidDriver") in session
    assert '"noReset", true' in session and "waitForIdleTimeout" in session


def test_every_reqnroll_step_has_exactly_one_definition_and_none_is_dead(platform):
    files = _kit(platform, "reqnroll")
    source = "\n".join(c for p, c in files.items() if p.startswith("StepDefinitions/"))
    expressions = re.findall(r'\[(?:Given|When|Then)\("(.+?)"\)\]', source)
    assert len(expressions) == len(set(expressions)), expressions
    lines = [
        re.sub(r"^\s+(Given|When|Then|And) ", "", ln)
        for p, c in files.items()
        if p.endswith(".feature")
        for ln in c.splitlines()
        if re.match(r"^\s+(Given|When|Then|And) ", ln)
    ]

    def matches(expression, line):
        return re.match("^" + re.escape(expression).replace(re.escape("{string}"), '"[^"]*"') + "$", line)

    for line in lines:
        assert len([e for e in expressions if matches(e, line)]) == 1, line
    for e in expressions:
        assert any(matches(e, ln) for ln in lines), f"dead step definition: {e!r}"


def _dotnet():
    return os.environ.get("DOTNET") or shutil.which("dotnet")


@pytest.mark.skipif(not os.environ.get("MOBISCOUT_REAL_COMPILE"), reason="needs the .NET 10 SDK + network")
def test_kit_builds_against_real_appium_nunit_and_reqnroll(platform, flavour, tmp_path):
    dotnet = _dotnet()
    if dotnet is None:
        pytest.skip("dotnet not installed")
    for rel, content in _kit(platform, flavour).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    proc = subprocess.run(
        [dotnet, "build", "-nologo", "-warnaserror"], cwd=tmp_path, capture_output=True, text=True, timeout=900
    )
    assert proc.returncode == 0, f"C# {flavour} kit does not build:\n{proc.stdout[-4000:]}\n{proc.stderr}"
