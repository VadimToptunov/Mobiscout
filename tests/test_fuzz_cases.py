"""Opt-in fuzz test generation: for a crawled form, emit adversarial-input tests
(empty / overflow / unicode / injection / format-string) that assert the app handles
each without advancing. Off unless the caller asks (the user chooses)."""

from framework.codegen.ir import ActionType
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.graph import fuzz_form_cases
from framework.crawler.to_codegen import build_test_model


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


def _form_result():
    login = CrawlScreen(
        "login",
        [
            _el("android.widget.EditText", rid="email", desc="Email"),
            _el("android.widget.EditText", rid="password", desc="Password"),
            _el("android.widget.Button", "Sign in", rid="signin"),
        ],
        platform="android",
    )
    home = CrawlScreen("home", [_el("android.widget.TextView", "Home", clk=False)], platform="android")
    res = CrawlResult(screens={"login": login, "home": home})
    res.transitions = [("login", _el("android.widget.Button", "Sign in", rid="signin"), "home")]
    return res


def test_fuzz_cases_cover_the_payload_categories():
    cases = fuzz_form_cases(_form_result(), "com.x")
    names = {c.name for c in cases}
    assert any("empty" in n for n in names)
    assert any("overflow" in n for n in names)
    assert any("sql_injection" in n for n in names)
    # each case types into the form, submits, and asserts (a real fuzz flow)
    c = cases[0]
    assert any(s.action == ActionType.TYPE for s in c.steps)
    assert any(s.action == ActionType.ASSERT for s in c.steps)


def test_fuzz_is_off_by_default_and_opt_in():
    res = _form_result()
    assert not any(c.name.startswith("fuzz_") for c in build_test_model(res, app_package="com.x").cases)
    assert any(c.name.startswith("fuzz_") for c in build_test_model(res, app_package="com.x", fuzz=True).cases)


def test_no_fuzz_cases_without_a_form():
    # A screen with no input has nothing to fuzz.
    res = CrawlResult(
        screens={"s": CrawlScreen("s", [_el("android.widget.TextView", "Hi", clk=False)], platform="android")}
    )
    assert fuzz_form_cases(res, "com.x") == []
