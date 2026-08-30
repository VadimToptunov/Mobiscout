"""A form case rendered as a Scenario Outline must ship exactly the data the crawl
used — one Examples row. A previous version appended a second, fabricated row
(user2@example.com, Secret123!, ...) while the assertions stayed literal, so an auth
or negative-form scenario got a second row that fed wrong input to a fixed
expectation and failed by construction."""

import re

import pytest

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
from framework.codegen.targets import get_emitter

_INVENTED = ("user2@example.com", "Secret123!", "0987654321")


def _login_model() -> TestModel:
    email = Selector(strategy=SelectorStrategy.ID, value="id/email")
    submit = Selector(strategy=SelectorStrategy.ID, value="id/submit")
    landing = Selector(strategy=SelectorStrategy.TEXT, value="Welcome")
    return TestModel(
        name="Login Flow",
        app_package="com.example.app",
        platform=Platform.ANDROID,
        cases=[
            TestCase(
                name="sign in",
                description="sign in",
                steps=[
                    Step(ActionType.LAUNCH, description="Open app"),
                    Step(ActionType.TYPE, selector=email, text="alice@example.com", description="type email"),
                    Step(ActionType.TAP, selector=submit, description="tap submit"),
                    # A literal assertion — the reason a fabricated 2nd input row would fail.
                    Step(
                        ActionType.ASSERT,
                        selector=landing,
                        assertion=AssertionType.VISIBLE,
                        description="Welcome is visible",
                    ),
                ],
            )
        ],
    )


@pytest.mark.parametrize("target", ["python_pytest_bdd", "js_cucumber", "java_cucumber"])
def test_form_outline_has_exactly_one_examples_row(target):
    feature = next(
        (c for name, c in get_emitter(target).emit(_login_model()).items() if name.endswith(".feature")),
        None,
    )
    assert feature is not None, f"{target} emitted no .feature file"
    assert "Scenario Outline" in feature, "a TYPE case should render as a Scenario Outline"

    # The Examples block: a header row plus exactly one data row.
    idx = feature.index("Examples:")
    block = feature[idx:]
    data_rows = [ln for ln in block.splitlines() if re.match(r"\s*\|", ln)]
    assert len(data_rows) == 2, f"expected header + 1 data row, got {len(data_rows)}: {data_rows}"

    for invented in _INVENTED:
        assert invented not in feature, f"{target} still emits fabricated Examples data ({invented})"
