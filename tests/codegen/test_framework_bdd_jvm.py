"""Cucumber-JVM suites (Java/Maven, Kotlin/Gradle) on the page objects: the BDD contract as
automated gates for both platforms, plus a REAL build and a Cucumber dry run.

The dry run resolves every feature step against the generated step definitions without a
device — an undefined or ambiguous step fails it — so "every step is wired" is proved by
Cucumber itself, not by a regex. It needs Maven/Gradle and network access, so it runs where
``MOBISCOUT_REAL_COMPILE=1`` (the CI codegen job) is set."""

import os
import re
import shutil
import subprocess

import pytest

from framework.codegen.framework_bdd_jvm import render_java_cucumber, render_kotlin_cucumber
from tests.codegen.test_framework_bdd_python import _framework  # the shared three-screen crawl

_RENDERERS = {"java": render_java_cucumber, "kotlin": render_kotlin_cucumber}
_BUILD = {"java": ("mvn", ["-q", "-B", "test"]), "kotlin": ("gradle", ["-q", "--no-daemon", "test"])}


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


@pytest.fixture(params=["android", "ios"])
def platform(request):
    """Every gate runs for both platforms — one suite, two drivers."""
    return request.param


@pytest.fixture(params=sorted(_RENDERERS))
def lang(request):
    """Both Cucumber-JVM languages."""
    return request.param


def _kit(platform, lang):
    return _RENDERERS[lang](_framework(platform))


def _steps(files):
    return {p: c for p, c in files.items() if "/steps/" in p}


def _expressions(files):
    source = "\n".join(_steps(files).values())
    return re.findall(r'@(?:Given|When|Then)\("(.+?)"\)', source)


def _feature_steps(files):
    lines = "\n".join(c for p, c in files.items() if p.endswith(".feature")).splitlines()
    return [
        re.sub(r"^\s+(Given|When|Then|And) ", "", ln) for ln in lines if re.match(r"^\s+(Given|When|Then|And) ", ln)
    ]


def _matches(expression, line):
    return re.match("^" + re.escape(expression).replace(re.escape("{string}"), '"[^"]*"') + "$", line) is not None


def test_layout(platform, lang):
    files = _kit(platform, lang)
    ext = "java" if lang == "java" else "kt"
    src = f"src/test/{lang}/mobiscout"
    for required in (f"{src}/RunCucumberTest.{ext}", f"{src}/support/Hooks.{ext}", f"{src}/support/Session.{ext}"):
        assert required in files, sorted(files)
    assert ("pom.xml" if lang == "java" else "build.gradle.kts") in files
    assert any(p.startswith("src/test/resources/features/") for p in files) and _steps(files)
    assert not any("/tests/" in p or p.endswith(("BaseTest.java", "BaseTest.kt", "testng.xml")) for p in files)


def test_every_step_has_exactly_one_definition_and_none_is_dead(platform, lang):
    files = _kit(platform, lang)
    expressions = _expressions(files)
    assert len(expressions) == len(set(expressions)), expressions
    lines = _feature_steps(files)
    for line in lines:
        hits = [e for e in expressions if _matches(e, line)]
        assert len(hits) == 1, f"{line!r} matches {hits}"
    for e in expressions:
        assert any(_matches(e, ln) for ln in lines), f"dead step definition: {e!r}"


def test_steps_are_one_call_on_a_page_object(platform, lang):
    for path, source in _steps(_kit(platform, lang)).items():
        for smell in ("AppiumBy", "findElement", "Thread.sleep", "WebDriverWait", "LOCATORS"):
            assert smell not in source, f"{smell!r} in {path}"
        bodies = re.findall(r"\) \{\n(.*?)\n    \}", source, re.S)
        assert bodies, source
        for body in bodies:
            statements = [ln for ln in body.splitlines() if ln.strip()]
            assert len(statements) == 1 and "Page(" in statements[0], body


def test_one_session_per_run_and_a_restart_per_scenario(platform, lang):
    files = _kit(platform, lang)
    ext = "java" if lang == "java" else "kt"
    hooks = files[f"src/test/{lang}/mobiscout/support/Hooks.{ext}"]
    session = files[f"src/test/{lang}/mobiscout/support/Session.{ext}"]
    assert "@Before" in hooks and "terminateApp(Session.APP)" in hooks and "activateApp(Session.APP)" in hooks
    assert ("IOSDriver" if platform == "ios" else "AndroidDriver") in session and "waitForIdleTimeout" in session


def test_build_pins_selenium_cucumber_and_junit(platform, lang):
    build = _kit(platform, lang)["pom.xml" if lang == "java" else "build.gradle.kts"]
    for pin in ("selenium-bom", "cucumber-bom", "junit-bom", "cucumber-junit-platform-engine", "junit-platform-suite"):
        assert pin in build, pin


@pytest.mark.skipif(not os.environ.get("MOBISCOUT_REAL_COMPILE"), reason="needs Maven/Gradle + network")
def test_kit_builds_and_every_step_resolves_in_a_cucumber_dry_run(platform, lang, tmp_path):
    tool, args = _BUILD[lang]
    exe = shutil.which(tool)
    if exe is None:
        pytest.skip(f"{tool} not installed")
    for rel, content in _kit(platform, lang).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    # Test-side only: resolve every step without executing one (no device, no session).
    (tmp_path / "src/test/resources/junit-platform.properties").write_text(
        "cucumber.execution.dry-run=true\n", encoding="utf-8"
    )
    proc = subprocess.run([exe, *args], cwd=tmp_path, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, f"{lang} Cucumber kit failed to build or dry-run:\n{proc.stdout}\n{proc.stderr}"
