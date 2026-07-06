"""Framework-structured output: Page Objects + conftest + POM-style tests, not a
flat smoke file."""

import ast

import pytest

from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.page_kit import build_framework_kit
from framework.crawler.to_codegen import build_test_model


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("OBSERVE_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("OBSERVE_ML_MODEL", "/nonexistent.pkl")


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


def _result():
    login = CrawlScreen(
        "login",
        [
            _el("android.widget.TextView", "Welcome back", clk=False),
            _el("android.widget.EditText", rid="email", desc="Email"),
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


def _kit():
    res = _result()
    model = build_test_model(res, app_package="com.x", app_activity=".Main")
    return build_framework_kit(res, model, "com.x")


def test_produces_pages_conftest_and_tests():
    files = _kit()
    assert "conftest.py" in files
    assert any(p.startswith("pages/") and p.endswith("_page.py") for p in files)
    assert "tests/test_navigation.py" in files


def test_all_files_are_valid_python():
    for path, content in _kit().items():
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
    model = build_test_model(res, app_package="com.x")
    for path, content in build_framework_kit(res, model, "com.x").items():
        if path.endswith(".py"):
            ast.parse(content)


def test_navigation_test_uses_page_objects():
    nav = _kit()["tests/test_navigation.py"]
    assert "from pages." in nav
    assert "(driver)." in nav and ".click()" in nav  # drives via the page object
