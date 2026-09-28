"""Framework-structured output: a Page-Object test framework (BasePage + a page per screen
+ a fast driver fixture + tests that read like intent), not a flat smoke file.

Beyond "it parses", these pin the senior-level contract as automated gates — so a
regression back to transcript-style output fails CI instead of reaching a user."""

import ast
import re

import pytest

from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.page_kit import build_framework_kit
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


def _result(platform="android"):
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
    """The senior contract holds for both platforms — one suite, two drivers."""
    return request.param


def _kit(result=None, platform="android"):
    res = result or _result(platform)
    model = build_test_model(res, app_package="com.x", app_activity=None if platform == "ios" else ".Main")
    return build_framework_kit(res, model, "com.x")


def _tests(files):
    return {p: c for p, c in files.items() if p.startswith("tests/test_")}


def test_produces_base_page_pages_fixture_and_tests(platform):
    files = _kit(platform=platform)
    assert "conftest.py" in files
    assert "pages/base_page.py" in files
    assert any(p.startswith("pages/") and p.endswith("_page.py") and p != "pages/base_page.py" for p in files)
    assert _tests(files), "expected test modules"


def test_all_files_are_valid_python(platform):
    for path, content in _kit(platform=platform).items():
        if path.endswith(".py"):
            ast.parse(content)  # raises on invalid syntax


def test_price_like_text_becomes_a_valid_identifier():
    # "$89.00" must not leak into a method name like `def $89.00`.
    res = CrawlResult(
        screens={
            "s": CrawlScreen(
                "s",
                [
                    _el("android.widget.TextView", "$89.00", clk=False),
                    _el("android.widget.Button", "Buy", rid="buy"),
                ],
                platform="android",
            )
        }
    )
    for path, content in _kit(res).items():
        if path.endswith(".py"):
            ast.parse(content)


def test_tests_drive_intention_methods_not_raw_elements(platform):
    # Locators and raw driver/element calls belong in the page layer. A test that clicks
    # elements or carries locators is a transcript, not a POM suite.
    for path, source in _tests(_kit(platform=platform)).items():
        assert "from pages." in source, path
        assert "Page(driver)" in source, path
        for smell in ("AppiumBy", "find_element", ".click()", ".send_keys(", "WebDriverWait"):
            assert smell not in source, f"{smell!r} leaked into {path}:\n{source}"


def test_form_filling_goes_through_intention_methods(platform):
    sources = "\n".join(_tests(_kit(platform=platform)).values())
    assert ".enter_email(" in sources  # typed via the page's intention, not send_keys
    assert sources.count("def test_") >= 2  # a real suite, not one smoke test


def test_plumbing_lives_only_in_the_base_page(platform):
    # Waiting / locating / scrolling written once in BasePage, not copy-pasted per screen.
    files = _kit(platform=platform)
    for path, source in files.items():
        if path.startswith("pages/") and path.endswith("_page.py") and path != "pages/base_page.py":
            assert "(BasePage)" in source, path
            for plumbing in ("WebDriverWait", "find_element", "def _find", "def _scroll_down"):
                assert plumbing not in source, f"{plumbing!r} duplicated in {path}"
    assert "def _find" in files["pages/base_page.py"]


def test_no_fixed_sleeps_anywhere(platform):
    for path, source in _kit(platform=platform).items():
        assert not re.search(r"\bsleep\(", source), f"fixed sleep in {path}"


def test_generated_code_is_pyflakes_clean(platform):
    # No unused imports, no unused variables, no undefined names — the generated code must
    # pass the linter a reviewer would run.
    pyflakes_api = pytest.importorskip("pyflakes.api")
    from pyflakes.reporter import Reporter
    import io

    for path, source in _kit(platform=platform).items():
        if not path.endswith(".py") or not source.strip():
            continue
        out, err = io.StringIO(), io.StringIO()
        count = pyflakes_api.check(source, path, Reporter(out, err))
        assert count == 0, f"pyflakes findings in {path}:\n{out.getvalue()}{err.getvalue()}"


def test_navigating_tap_returns_the_next_page(platform):
    sources = "\n".join(_tests(_kit(platform=platform)).values())
    assert re.search(r"catalog_page = \w+_page\.tap_sign_in\(\)", sources), sources


def test_negative_case_does_not_claim_it_navigated(platform):
    # Invalid input must NOT get past the form, so the test must not bind the page the
    # tap would otherwise open.
    sources = _tests(_kit(platform=platform))
    rejects = next(s for s in sources.values() if "def test_rejects_invalid_input" in s)
    body = rejects.split("def test_rejects_invalid_input", 1)[1]
    assert "= welcome_back_page.tap_sign_in()" not in body, body
    assert "welcome_back_page.tap_sign_in()" in body, body


def test_one_appium_session_per_run_with_an_app_restart_per_test(platform):
    # Fast by design: a new session per test costs 5-10 s; a cold app restart ~1-2 s.
    conftest = _kit(platform=platform)["conftest.py"]
    assert ("XCUITestOptions" if platform == "ios" else "UiAutomator2Options") in conftest
    assert 'scope="session"' in conftest
    assert "activate_app" in conftest and "terminate_app" in conftest


def test_page_is_named_after_the_screen_title_not_a_paragraph():
    res = CrawlResult(
        screens={
            "s": CrawlScreen(
                "s",
                [
                    _el("android.widget.TextView", "Generate realistic test data — cards, IBANs and more.", clk=False),
                    _el("android.widget.TextView", "Tools", clk=False),
                    _el("android.widget.Button", "Open", rid="open"),
                ],
                platform="android",
            )
        }
    )
    files = _kit(res)
    assert "pages/tools_page.py" in files, sorted(files)
    assert not any("generate_realistic" in p for p in files), sorted(files)


def test_test_names_are_not_numbered(platform):
    for source in _tests(_kit(platform=platform)).values():
        assert not re.search(r"def test_\w+_\d+\(", source), source
