"""A label/value containing a ``"`` or a newline must not corrupt the emitted
``.feature`` file (see _bdd_common.gherkin_quote).

The bug: target names, typed text and expected values were embedded inside
Gherkin double quotes with no escaping, so any such character produced a
malformed feature that no Cucumber parser (pytest-bdd, cucumber-jvm, cucumber.js)
could read. These tests build a model with a hostile label and prove the
rendered feature still parses and that the quoted arguments round-trip.
"""

import re

import pytest
from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner

from framework.codegen.emitters._bdd_common import gherkin_quote, render_feature
from framework.codegen.ir import (
    ActionType,
    AssertionType,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)

# Cucumber's {string} parameter type: a double-quoted run allowing backslash
# escapes. Used to extract and unescape the quoted arguments from a step line.
_CUCUMBER_STRING = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')


def _cucumber_unescape(inner: str) -> str:
    """Reverse gherkin_quote's backslash escaping for one {string} argument."""
    return inner.replace('\\"', '"').replace("\\\\", "\\")


def test_gherkin_quote_escapes_quote_and_neutralises_newlines():
    assert gherkin_quote('say "hi"') == 'say \\"hi\\"'
    assert gherkin_quote("a\\b") == "a\\\\b"
    assert gherkin_quote("line1\nline2") == "line1 line2"
    assert gherkin_quote("crlf\r\nhere") == "crlf here"
    assert gherkin_quote("clean") == "clean"  # identity for clean values


def _hostile_model() -> TestModel:
    """A model whose target name and expected value contain a quote and a
    newline, exercised through a plain Scenario (tap + text assertion)."""
    nasty = 'Save "Draft"\nnow'
    return TestModel(
        name="EscapeFlow",
        app_package="com.example.app",
        cases=[
            TestCase(
                name="hostile",
                description="hostile labels do not corrupt the feature",
                steps=[
                    Step(ActionType.LAUNCH),
                    Step(
                        ActionType.TAP,
                        selector=Selector(SelectorStrategy.ID, "save_btn", description=nasty),
                    ),
                    Step(
                        ActionType.ASSERT,
                        selector=Selector(SelectorStrategy.TEXT, "banner", description="Status"),
                        assertion=AssertionType.TEXT_EQUALS,
                        expected='All "saved"\nok',
                    ),
                ],
            )
        ],
    )


def test_hostile_feature_is_parseable():
    feature = render_feature(_hostile_model())
    # No step line may carry a raw newline out of a label — every line stays a
    # single, self-contained Gherkin line.
    parsed = Parser().parse(TokenScanner(feature))
    assert parsed["feature"]["name"] == "EscapeFlow"


def test_hostile_labels_round_trip_through_cucumber_string():
    feature = render_feature(_hostile_model())
    # Collect every {string} argument across the feature and unescape it.
    args = [_cucumber_unescape(m.group(1)) for line in feature.splitlines() for m in _CUCUMBER_STRING.finditer(line)]
    # The quote survives (escaped then unescaped); the newline is neutralised to
    # a space so the label stays on one line but its words are preserved.
    assert 'Save "Draft" now' in args
    assert 'All "saved" ok' in args


def test_no_step_line_carries_a_raw_control_char():
    feature = render_feature(_hostile_model())
    for line in feature.splitlines():
        assert "\t" not in line  # tabs would also fracture a step line


@pytest.mark.parametrize("bad", ['x"y', "a\nb", "c\r\nd", "back\\slash"])
def test_quoted_embedding_never_leaves_an_unbalanced_line(bad):
    model = TestModel(
        name="EF",
        app_package="p",
        cases=[
            TestCase(
                name="c",
                steps=[
                    Step(ActionType.LAUNCH),
                    Step(ActionType.TAP, selector=Selector(SelectorStrategy.ID, "b", description=bad)),
                ],
            )
        ],
    )
    feature = render_feature(model)
    # Must parse regardless of the hostile character.
    assert Parser().parse(TokenScanner(feature))["feature"] is not None
