"""Coverage-diff: keep only cases that touch a locator not already tested, so a
crawl of a new feature yields tests for that feature alone."""

from framework.codegen.ir import (
    ActionType,
    AssertionType,
    Platform,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)
from framework.crawler.coverage import case_is_new, existing_test_text, filter_to_new


def _sel(value, desc=""):
    return Selector(SelectorStrategy.ACCESSIBILITY_ID, value, description=desc)


def _case(name, *values):
    steps = [Step(ActionType.ASSERT, selector=_sel(v), assertion=AssertionType.VISIBLE) for v in values]
    return TestCase(name=name, steps=steps)


def _model(cases):
    return TestModel(name="F", app_package="com.x", platform=Platform.ANDROID, cases=cases)


EXISTING = """
    driver.find_element(AppiumBy.ACCESSIBILITY_ID, "login_btn")
    driver.find_element(AppiumBy.ACCESSIBILITY_ID, "email_field")
"""


def test_case_touching_only_covered_locators_is_dropped():
    assert not case_is_new(_case("known", "login_btn", "email_field"), EXISTING)


def test_case_touching_a_new_locator_is_kept():
    assert case_is_new(_case("mixed", "email_field", "new_feature_button"), EXISTING)


def test_filter_keeps_only_new_and_reports():
    model = _model(
        [
            _case("old_login", "login_btn", "email_field"),  # fully covered -> dropped
            _case("new_kyc", "scan_document_button"),  # new -> kept
            _case("new_totp", "otp_field"),  # new -> kept
        ]
    )
    trimmed, report = filter_to_new(model, EXISTING)
    assert [c.name for c in trimmed.cases] == ["new_kyc", "new_totp"]
    assert report.total_cases == 3 and report.new_cases == 2 and report.covered_cases == 1
    assert "2/3" in report.summary()


def test_existing_test_text_reads_supported_files(tmp_path):
    (tmp_path / "test_login.py").write_text('AppiumBy.ACCESSIBILITY_ID, "login_btn"')
    (tmp_path / "LoginTest.java").write_text('accessibilityId("email_field")')
    (tmp_path / "notes.md").write_text("scan_document_button")  # .md not scanned
    text = existing_test_text(tmp_path)
    assert "login_btn" in text and "email_field" in text
    assert "scan_document_button" not in text


def test_missing_path_is_empty_so_everything_is_new():
    model = _model([_case("a", "x"), _case("b", "y")])
    trimmed, report = filter_to_new(model, existing_test_text(__import__("pathlib").Path("/no/such/dir")))
    assert report.new_cases == 2


def test_pipeline_only_new_writes_gap_and_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSERVE_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("OBSERVE_ML_MODEL", "/nonexistent.pkl")
    from framework.crawler.pipeline import run_kit
    from tests.test_crawler import APP, FakeDriver

    # Existing tests already cover the fake app's login button -> its case drops.
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "test_login.py").write_text('AppiumBy.ID, "id/login"\nAppiumBy.ID, "id/help"')

    out = tmp_path / "kit"
    summary = run_kit(
        {
            "package": APP,
            "targets": ["python_pytest"],
            "output": str(out),
            "only_new": True,
            "existing_tests": str(existing),
        },
        driver=FakeDriver(),
    )
    assert summary["gap"] is not None and "case(s) are new" in summary["gap"]
    assert (out / "coverage_gap.txt").exists()
