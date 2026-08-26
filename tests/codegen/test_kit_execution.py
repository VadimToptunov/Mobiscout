"""Execute an emitted kit (flat python_pytest and the POM `--style pom` layout) against a
device-free fake Appium and assert it goes green — the product's core promise ("generated
tests pass") turned from a py_compile guess into an executed check.

The fake app (tests/support/kit_fake_conftest.py) is a screen state-machine built here from
the CrawlResult, independently of the emitter: locators come from `selector_for` + the
emitter's own `by_value` (so model and kit agree on wire strings), while *which screen an
element is on* and *where a tap goes* come from the crawl structure — so a codegen bug that
asserts an element the flow never reached fails for real. Every screen registers the WHOLE
ranked chain the kit emits, primary and fallbacks alike, so a self-healing fallback that
binds to the wrong element is visible here rather than only on a real device.

Negative controls prove the harness has teeth: deliberately broken apps (navigation removed,
validation missing) must turn the kit red.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from framework.codegen import get_emitter
from framework.codegen.emitters._python_common import by_value
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.page_kit import build_framework_kit
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


def _chain(sel, platform):
    """Every (by, value) the emitted kit will try for this selector — primary first, then
    the self-healing fallbacks. Registering only the primary (as this harness once did)
    left every fallback tier unreachable at kit runtime, so a fallback that resolves the
    WRONG element — the next screen's identically-labelled button — passed CI unseen."""
    return [_runtime_locator(s, platform) for s in [sel, *sel.fallbacks]]


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
                locs.extend([list(loc) for loc in _chain(sel, screen.platform)])
        screens.append(locs)
    transitions = []
    for from_fp, element, to_fp in result.transitions:
        if from_fp not in idx or to_fp not in idx:
            continue
        owned = _owned(result.screens[from_fp], package)
        sel = selector_for(element, owned, result.screens[from_fp].platform)
        if sel is None:
            continue
        # However the kit located the control, tapping it does the same thing.
        for by, value in _chain(sel, result.screens[from_fp].platform):
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


def _run_pytest(kit: Path, model: dict, verbose: bool = False) -> subprocess.CompletedProcess:
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
            # -v names the tests that PASSED, which is what a "green on a broken app"
            # check needs — -q only names failures.
            "-v" if verbose else "-q",
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


def _element_chain(result: CrawlResult, fingerprint: str, index: int):
    """The full locator chain the kit emits for one element of one screen."""
    screen = result.screens[fingerprint]
    owned = _owned(screen, "com.x")
    return _chain(selector_for(owned[index], owned, screen.platform), screen.platform)


def test_find_scrolls_to_reach_a_below_fold_element(tmp_path):
    # Move a start-screen element below the fold: present only after a scroll. The kit
    # must still pass, which it can only do if the generated _find scrolls on miss.
    result = _shop()
    kit = _emit_kit(result, tmp_path)
    model = _fake_app(result, "com.x")
    # Hide EVERY tier of one element's chain. Hiding only the primary would let _find
    # self-heal to a fallback and return without ever scrolling.
    hidden = set(_element_chain(result, "login", -1))  # the Sign-in button
    model["screens"][0] = [loc for loc in model["screens"][0] if tuple(loc) not in hidden]
    model.setdefault("reveals", []).extend([[0, by, value] for by, value in hidden])
    proc = _run_pytest(kit, model)
    assert proc.returncode == 0, f"_find did not scroll to the below-fold element:\n{proc.stdout}\n{proc.stderr}"


def test_find_self_heals_to_a_fallback_locator(tmp_path):
    # Remove the PRIMARY tier of one element, keeping its fallback: the kit must still
    # pass, and can only do so by walking the whole chain. This is what makes the
    # fallback tiers — and a fallback matching the wrong element — visible to CI.
    result = _shop()
    kit = _emit_kit(result, tmp_path)
    model = _fake_app(result, "com.x")
    chain = _element_chain(result, "login", 1)  # the email field: accessibility-id, then resource-id
    assert len(chain) > 1, "fixture must have a fallback tier to exercise"
    model["screens"][0] = [loc for loc in model["screens"][0] if tuple(loc) != chain[0]]
    proc = _run_pytest(kit, model)
    assert proc.returncode == 0, f"kit did not self-heal to the fallback:\n{proc.stdout}\n{proc.stderr}"


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


def _wizard() -> CrawlResult:
    """A two-step wizard whose steps carry the same "Continue" label — the shape that lets
    a self-healing fallback bind to the NEXT screen's button. The phone field is one the
    fake app does not validate, so this app ACCEPTS "abc" and advances: an app with broken
    validation, on which the negative case must go red."""
    step1 = CrawlScreen(
        "step1",
        [
            _el("android.widget.TextView", "Your phone", clk=False),
            _el("android.widget.EditText", rid="phone", desc="Phone number"),
            _el("android.widget.Button", "Continue", rid="cont_phone"),
        ],
        platform="android",
    )
    step2 = CrawlScreen(
        "step2",
        [
            _el("android.widget.TextView", "Your name", clk=False),
            _el("android.widget.EditText", rid="fullname", desc="Full name"),
            _el("android.widget.Button", "Continue", rid="cont_name"),
        ],
        platform="android",
    )
    res = CrawlResult(screens={"step1": step1, "step2": step2})
    res.transitions = [("step1", _el("android.widget.Button", "Continue", rid="cont_phone"), "step2")]
    return res


def test_negative_case_fails_when_the_app_accepts_invalid_input(tmp_path):
    # The flagship false-green: "invalid input is rejected" used to be asserted on the
    # submit control *with its fallback chain*, so the next wizard step's identical
    # "Continue" satisfied it and the kit went green while the app had accepted "abc"
    # and navigated away.
    result = _wizard()
    kit = _emit_kit(result, tmp_path)
    proc = _run_pytest(kit, _fake_app(result, "com.x"))
    assert proc.returncode != 0, f"an app that accepts invalid input must fail the negative case:\n{proc.stdout}"
    assert "rejects_invalid_input" in proc.stdout, f"a different test failed, not the negative one:\n{proc.stdout}"


def _unlabelled_destination() -> CrawlResult:
    """A destination with nothing to locate but its position — the case in which the
    landmark used to fall back to `(//android.view.View[...])[1]`, which matches the
    SOURCE screen just as well."""
    login = CrawlScreen(
        "login",
        [
            _el("android.view.View"),
            _el("android.widget.TextView", "Welcome back", clk=False),
            _el("android.widget.Button", "Sign in", rid="signin"),
        ],
        platform="android",
    )
    home = CrawlScreen("home", [_el("android.view.View"), _el("android.view.View")], platform="android")
    res = CrawlResult(screens={"login": login, "home": home})
    res.transitions = [("login", _el("android.widget.Button", "Sign in", rid="signin"), "home")]
    return res


def test_no_navigation_test_rests_on_a_positional_locator(tmp_path):
    result = _unlabelled_destination()
    kit = _emit_kit(result, tmp_path)
    source = "\n".join(p.read_text(encoding="utf-8") for p in kit.glob("test_*.py"))
    assert "(//android.view.View" not in source, f"a positional locator is asserted on:\n{source}"
    # Executed: with navigation completely broken, no navigation test may report PASSED.
    broken = _fake_app(result, "com.x")
    broken["transitions"] = []
    proc = _run_pytest(kit, broken, verbose=True)
    assert not re.search(
        r"tapping_sign_in\S*\s+PASSED", proc.stdout
    ), f"a navigation test passed while navigation was broken:\n{proc.stdout}"


# --- the POM kit (--style pom): pages/ + conftest + tests that drive the page objects ---


def _emit_pom_kit(result: CrawlResult, tmp: Path) -> Path:
    """The framework-structured kit, run device-free. Its own conftest carries the driver
    fixture the POM tests need, so the fake app is PREPENDED to it rather than replacing
    it — the generated `webdriver.Remote(...)` then runs against the fake."""
    model = build_test_model(result, app_package="com.x", app_activity=".Main")
    kit = tmp / "pom"
    for name, content in build_framework_kit(result, model, "com.x").items():
        path = kit / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    conftest = kit / "conftest.py"
    conftest.write_text(
        _CONFTEST.read_text(encoding="utf-8") + "\n\n" + conftest.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return kit


def _shared_label() -> CrawlResult:
    """A header and the button under it both read "Sign in" — the accessor-name collision
    that used to delete the button from the page object, taking every step that targets
    it with it."""
    login = CrawlScreen(
        "login",
        [
            _el("android.widget.TextView", "Sign in", clk=False),
            _el("android.widget.EditText", rid="email", desc="Email address"),
            _el("android.widget.Button", "Sign in", rid="signin"),
        ],
        platform="android",
    )
    catalog = CrawlScreen(
        "catalog",
        [
            _el("android.widget.TextView", "Catalog", clk=False),
            _el("android.widget.Button", "Product", rid="prod"),
        ],
        platform="android",
    )
    res = CrawlResult(screens={"login": login, "catalog": catalog})
    res.transitions = [("login", _el("android.widget.Button", "Sign in", rid="signin"), "catalog")]
    return res


def _same_title() -> CrawlResult:
    """Two screens titled the same — their page classes are de-duplicated (AccountPage /
    Account2Page) and the navigation test has to drive the second one."""
    s1 = CrawlScreen(
        "s1",
        [
            _el("android.widget.TextView", "Account", clk=False),
            _el("android.widget.Button", "Open", rid="open"),
        ],
        platform="android",
    )
    s2 = CrawlScreen(
        "s2",
        [
            _el("android.widget.TextView", "Account", clk=False),
            _el("android.widget.Button", "Deposit", rid="dep"),
        ],
        platform="android",
    )
    res = CrawlResult(screens={"s1": s1, "s2": s2})
    res.transitions = [("s1", _el("android.widget.Button", "Open", rid="open"), "s2")]
    return res


def _shared_chrome() -> CrawlResult:
    """Both screens open with the same logo — a landmark taken in dump order is already on
    screen before the tap, so the navigation test passes without navigating."""
    home = CrawlScreen(
        "home",
        [
            _el("android.widget.ImageView", desc="Logo", clk=False),
            _el("android.widget.TextView", "Home", clk=False),
            _el("android.widget.Button", "Sign in", rid="signin"),
        ],
        platform="android",
    )
    catalog = CrawlScreen(
        "catalog",
        [
            _el("android.widget.ImageView", desc="Logo", clk=False),
            _el("android.widget.TextView", "Catalog", clk=False),
            _el("android.widget.Button", "Product", rid="prod"),
        ],
        platform="android",
    )
    res = CrawlResult(screens={"home": home, "catalog": catalog})
    res.transitions = [("home", _el("android.widget.Button", "Sign in", rid="signin"), "catalog")]
    return res


def test_pom_kit_runs_green_when_two_elements_share_a_label(tmp_path):
    # The dropped button used to take the login->catalog tap with it, so the POM tests
    # asserted the catalog screen without ever navigating there — red on a working app.
    result = _shared_label()
    kit = _emit_pom_kit(result, tmp_path)
    proc = _run_pytest(kit, _fake_app(result, "com.x"))
    assert proc.returncode == 0, f"POM kit failed against a healthy app:\n{proc.stdout}\n{proc.stderr}"


def test_pom_flow_tests_always_carry_an_assertion(tmp_path):
    # A case whose assertions were all dropped used to be emitted anyway: a test that
    # types a value, asserts nothing and passes unconditionally.
    result = _shared_label()
    kit = _emit_pom_kit(result, tmp_path)
    flows = (kit / "tests" / "test_flows.py").read_text(encoding="utf-8")
    bodies = flows.split("\ndef test_")[1:]
    assert bodies, "expected flow tests"
    for body in bodies:
        assert "assert " in body, f"flow test with no assertion:\ndef test_{body}"


def test_pom_navigation_drives_the_deduplicated_page_class(tmp_path):
    # Two screens titled "Account" -> AccountPage + Account2Page. Re-deriving the class
    # name from the title sent the test to AccountPage, which has no deposit() at all.
    result = _same_title()
    kit = _emit_pom_kit(result, tmp_path)
    nav = (kit / "tests" / "test_navigation.py").read_text(encoding="utf-8")
    assert "Account2Page" in nav, f"navigation test never reaches the second page class:\n{nav}"
    proc = _run_pytest(kit, _fake_app(result, "com.x"))
    assert proc.returncode == 0, f"POM kit failed against a healthy app:\n{proc.stdout}\n{proc.stderr}"


def test_pom_navigation_fails_when_the_tap_navigates_nowhere(tmp_path):
    # The landmark must be distinctive to the destination. With the logo (shared chrome)
    # as landmark, this kit passed with the transition removed entirely.
    result = _shared_chrome()
    kit = _emit_pom_kit(result, tmp_path)
    healthy = _run_pytest(kit, _fake_app(result, "com.x"))
    assert healthy.returncode == 0, f"POM kit failed against a healthy app:\n{healthy.stdout}\n{healthy.stderr}"
    broken = _fake_app(result, "com.x")
    broken["transitions"] = []
    proc = _run_pytest(kit, broken)
    assert proc.returncode != 0, f"broken navigation should fail the POM kit but passed:\n{proc.stdout}"
    assert "test_navigate_1" in proc.stdout, f"the navigation test is not the one that failed:\n{proc.stdout}"


def test_pom_conftest_reads_the_appium_server_env_var():
    # Every other target honours MOBISCOUT_APPIUM_SERVER and the README written into the
    # same directory documents it; a hard-coded localhost cannot reach the remote hub or
    # cloud grid the crawl itself ran against.
    result = _shared_label()
    model = build_test_model(result, app_package="com.x", app_activity=".Main")
    conftest = build_framework_kit(result, model, "com.x")["conftest.py"]
    assert 'os.environ.get("MOBISCOUT_APPIUM_SERVER", "http://localhost:4723")' in conftest


# --- a non-pytest target: the same crawl must not pass in one target and fail in another ---


def _emit_bdd_kit(result: CrawlResult, tmp: Path) -> Path:
    """The python_pytest_bdd kit (feature file + step definitions). Its step module owns
    the driver fixture, so the fake app replaces the conftest outright."""
    model = build_test_model(result, app_package="com.x", app_activity=".Main")
    kit = tmp / "bdd"
    for name, content in get_emitter("python_pytest_bdd").emit(model).items():
        path = kit / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    shutil.copy(_CONFTEST, kit / "conftest.py")
    return kit


def test_bdd_kit_reaches_a_below_fold_element_like_the_pytest_kit(tmp_path):
    # One crawl, one app, two targets. The BDD find() used to give up where the
    # imperative one scrolled, so the same app was green as pytest and red as BDD.
    result = _shared_chrome()
    model = _fake_app(result, "com.x")
    hidden = set(_element_chain(result, "home", -1))  # the Sign-in button, below the fold
    model["screens"][0] = [loc for loc in model["screens"][0] if tuple(loc) not in hidden]
    model.setdefault("reveals", []).extend([[0, by, value] for by, value in hidden])

    flat = _run_pytest(_emit_kit(result, tmp_path), model)
    assert flat.returncode == 0, f"flat kit did not pass:\n{flat.stdout}\n{flat.stderr}"
    bdd = _run_pytest(_emit_bdd_kit(result, tmp_path), model)
    assert bdd.returncode == 0, f"BDD kit did not scroll to the below-fold element:\n{bdd.stdout}\n{bdd.stderr}"
