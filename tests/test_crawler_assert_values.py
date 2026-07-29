"""Opt-in value pinning: --assert-values makes the crawler ALSO emit TEXT_EQUALS
steps that pin observed static text, so a defect that changes a displayed value
(money rounding, P&L sign, wrong validation output) fails the generated test.

Default OFF must leave the VISIBLE-only output untouched — that invariant is
covered here (no TEXT_EQUALS by default) and by the codegen golden fixtures,
which never pass assert_values.
"""

import pytest

from framework.codegen.emitters._python_common import py_str
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
from framework.codegen import get_emitter
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import build_test_model


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


def _screen():
    # A landmark, a money value (looks 'dynamic' but IS the thing to pin), a
    # single-char value (skipped), and an actionable button (a control, not a value).
    return CrawlScreen(
        "product",
        [
            _el("android.widget.TextView", "Running Shoes", rid="title", clk=False),  # landmark value
            _el("android.widget.TextView", "$89.00", rid="price", clk=False),  # money value -> pin
            _el("android.widget.TextView", "x", rid="tiny", clk=False),  # single char -> skip
            _el("android.widget.Button", "Add to cart", rid="add"),  # control label -> not a value
        ],
        platform="android",
    )


def _text_equals_steps(model):
    return [
        s
        for c in model.cases
        for s in c.steps
        if s.action is ActionType.ASSERT and s.assertion is AssertionType.TEXT_EQUALS
    ]


def test_assert_values_off_by_default_emits_no_text_equals():
    model = build_test_model(CrawlResult(screens={"product": _screen()}), app_package="com.x")
    assert _text_equals_steps(model) == []


def test_assert_values_pins_observed_text_with_expected_equal_to_capture():
    model = build_test_model(CrawlResult(screens={"product": _screen()}), app_package="com.x", assert_values=True)
    pinned = _text_equals_steps(model)
    assert pinned, "assert_values=True should emit at least one TEXT_EQUALS step"
    expected = {s.expected for s in pinned}
    # The money value is pinned with expected == the captured element text ...
    assert "$89.00" in expected
    assert "Running Shoes" in expected
    # ... while the single-char value and the tapped control label are not pinned.
    assert "x" not in expected
    assert "Add to cart" not in expected


def test_assert_values_keeps_the_existing_visible_assertions():
    """Value pinning is additive: the VISIBLE checks are unchanged, TEXT_EQUALS
    is layered on top."""
    base = build_test_model(CrawlResult(screens={"product": _screen()}), app_package="com.x")
    pinned = build_test_model(CrawlResult(screens={"product": _screen()}), app_package="com.x", assert_values=True)

    def _visible(model):
        return {
            (s.selector.value, s.assertion)
            for c in model.cases
            for s in c.steps
            if s.action is ActionType.ASSERT and s.assertion is AssertionType.VISIBLE
        }

    assert _visible(base) == _visible(pinned)  # VISIBLE set unchanged
    assert _text_equals_steps(pinned) and not _text_equals_steps(base)


def test_python_pytest_emitter_renders_text_equals_assertion():
    """A TEXT_EQUALS step must render as a `.text == "<value>"` assertion."""
    value = "€1,204.55"
    model = TestModel(
        name="ValuePin",
        app_package="com.example.app",
        platform=Platform.ANDROID,
        cases=[
            TestCase(
                name="balance_shows_expected_value",
                steps=[
                    Step(ActionType.LAUNCH, description="Open app"),
                    Step(
                        ActionType.ASSERT,
                        selector=Selector(SelectorStrategy.ID, "com.example.app:id/balance"),
                        assertion=AssertionType.TEXT_EQUALS,
                        expected=value,
                        description=f"balance shows {value!r}",
                    ),
                ],
            )
        ],
    )
    src = "\n".join(get_emitter("python_pytest").emit(model).values())
    assert f".text == {py_str(value)}" in src
