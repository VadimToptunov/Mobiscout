"""Shared IR fixtures for codegen golden tests."""

import pytest

# Golden files are generated sources named test_*.py — they are fixtures, not
# tests. Keep pytest from collecting and trying to run them.
collect_ignore_glob = ["golden/*"]

from framework.codegen.ir import (
    ActionType,
    AssertionType,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)


@pytest.fixture()
def login_model() -> TestModel:
    """A representative model exercising every action/assertion kind plus
    a fallback chain. Used to pin every emitter's output via golden files."""
    return TestModel(
        name="LoginFlow",
        app_package="com.example.app",
        app_activity=".MainActivity",
        description="Generated login flow used for golden tests.",
        cases=[
            TestCase(
                name="login",
                description="User can log in with valid credentials",
                steps=[
                    Step(ActionType.LAUNCH, description="Open app"),
                    Step(
                        ActionType.TYPE,
                        selector=Selector(
                            SelectorStrategy.ID,
                            "user_field",
                            score=0.9,
                            fallbacks=[Selector(SelectorStrategy.XPATH, "//input[1]", score=0.3)],
                        ),
                        text="alice@example.com",
                        description="Enter email",
                    ),
                    Step(
                        ActionType.TAP,
                        selector=Selector(SelectorStrategy.ACCESSIBILITY_ID, "login_btn", score=0.95),
                        description="Tap login",
                    ),
                    Step(ActionType.WAIT, timeout=3, description="Wait for home"),
                    Step(ActionType.SWIPE, direction="up", description="Swipe up to reveal content"),
                    Step(ActionType.BACK, description="Dismiss a dialog"),
                    Step(
                        ActionType.ASSERT,
                        selector=Selector(SelectorStrategy.TEXT, "Welcome", score=0.6),
                        assertion=AssertionType.VISIBLE,
                        description="Welcome message shown",
                    ),
                ],
            )
        ],
    )


@pytest.fixture()
def flutter_model() -> TestModel:
    """A Flutter (Route B) login flow exercising every integration-driver finder
    tier — ValueKey, semantics label, visible text and bare widget type — plus a
    Flutter-only fallback chain. Pins the Flutter-capable emitters' output and the
    scoring order (ValueKey > semantics > text > type)."""
    return TestModel(
        name="FlutterLoginFlow",
        app_package="com.example.flutterapp",
        app_activity=".MainActivity",
        description="Generated Flutter (Route B) login flow used for golden tests.",
        toolkit="flutter",
        cases=[
            TestCase(
                name="login",
                description="User can log in with valid credentials",
                steps=[
                    Step(ActionType.LAUNCH, description="Open app"),
                    Step(
                        ActionType.TYPE,
                        # ValueKey wins over the semantics-label fallback.
                        selector=Selector(
                            SelectorStrategy.FLUTTER_KEY,
                            "email_field",
                            score=0.95,
                            fallbacks=[Selector(SelectorStrategy.FLUTTER_SEMANTICS, "Email", score=0.9)],
                        ),
                        text="alice@example.com",
                        description="Enter email",
                    ),
                    Step(
                        ActionType.TAP,
                        # No key: semantics label, falling back to the visible text.
                        selector=Selector(
                            SelectorStrategy.FLUTTER_SEMANTICS,
                            "Log in",
                            score=0.9,
                            fallbacks=[Selector(SelectorStrategy.FLUTTER_TEXT, "Log in", score=0.6)],
                        ),
                        description="Tap login",
                    ),
                    Step(ActionType.WAIT, timeout=3, description="Wait for home"),
                    Step(
                        ActionType.TAP,
                        # Nothing but a widget type — the last-resort positional tier.
                        selector=Selector(SelectorStrategy.FLUTTER_TYPE, "IconButton", score=0.3),
                        description="Open the menu",
                    ),
                    Step(
                        ActionType.ASSERT,
                        selector=Selector(SelectorStrategy.FLUTTER_TEXT, "Welcome", score=0.6),
                        assertion=AssertionType.VISIBLE,
                        description="Welcome message shown",
                    ),
                ],
            )
        ],
    )
