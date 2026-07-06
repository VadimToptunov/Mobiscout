"""BDD steps must be parameterized: form-filling cases become Scenario Outlines
with Examples tables, and many-element state checks collapse to an outline over
"<element>"."""

from framework.codegen.emitters._bdd_common import render_feature
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


def _sel(value):
    return Selector(SelectorStrategy.ACCESSIBILITY_ID, value, description=value)


def _model(cases):
    return TestModel(name="Flow", app_package="com.x", platform=Platform.ANDROID, cases=cases)


def test_form_case_becomes_scenario_outline_with_examples():
    case = TestCase(
        name="login",
        description="Login",
        steps=[
            Step(ActionType.LAUNCH),
            Step(ActionType.TYPE, selector=_sel("Email"), text="test@example.com"),
            Step(ActionType.TYPE, selector=_sel("Password"), text="Password123!"),
            Step(ActionType.TAP, selector=_sel("Sign in")),
            Step(ActionType.ASSERT, selector=_sel("Catalog"), assertion=AssertionType.VISIBLE),
        ],
    )
    feature = render_feature(_model([case]))
    assert "Scenario Outline: Login" in feature
    assert 'I enter "<email>" into "Email"' in feature
    assert 'I enter "<password>" into "Password"' in feature
    assert "Examples:" in feature
    assert "| email | password |" in feature
    assert "| test@example.com | Password123! |" in feature  # the tester's starting data


def test_state_check_collapses_to_element_outline():
    case = TestCase(
        name="screen_1_state",
        description="Screen 1 state",
        steps=[
            Step(ActionType.LAUNCH),
            Step(ActionType.ASSERT, selector=_sel("Email"), assertion=AssertionType.VISIBLE),
            Step(ActionType.ASSERT, selector=_sel("Email"), assertion=AssertionType.ENABLED),  # folded away
            Step(ActionType.ASSERT, selector=_sel("Password"), assertion=AssertionType.VISIBLE),
            Step(ActionType.ASSERT, selector=_sel("Sign in"), assertion=AssertionType.VISIBLE),
        ],
    )
    feature = render_feature(_model([case]))
    assert "Scenario Outline: Screen 1 state" in feature
    assert 'Then "<element>" is visible' in feature
    assert "| element |" in feature
    for el in ("Email", "Password", "Sign in"):
        assert f"| {el} |" in feature
    # ENABLED assert folded away -> not duplicated as a separate line
    assert '"Email" is enabled' not in feature


def test_plain_navigation_stays_a_scenario():
    case = TestCase(
        name="nav",
        description="Nav",
        steps=[
            Step(ActionType.LAUNCH),
            Step(ActionType.TAP, selector=_sel("Sign in")),
            Step(ActionType.ASSERT, selector=_sel("Catalog"), assertion=AssertionType.VISIBLE),
        ],
    )
    feature = render_feature(_model([case]))
    assert "Scenario: Nav" in feature and "Scenario Outline" not in feature
