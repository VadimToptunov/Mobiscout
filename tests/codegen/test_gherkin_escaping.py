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

from framework.codegen.emitters._bdd_common import collect_targets, gherkin_quote, render_feature
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
    # A target name is canonicalised (a double quote becomes a single one) so the
    # same text can key the LOCATORS registry — see the contract test below. A
    # plain value only needs escaping, so its quote survives verbatim. Both keep
    # their words: the newline is neutralised to a space, not dropped.
    assert "Save 'Draft' now" in args
    assert 'All "saved" ok' in args


def test_registry_keys_are_the_feature_targets_verbatim():
    """The LOCATORS registry key and the target written into the .feature must be
    the same text. The generated step definition looks the captured argument up in
    that registry, so escaping applied to one side only is a KeyError (pytest-bdd)
    or a null/undefined locator list (Cucumber-JVM, Cucumber.js) at run time."""
    model = _hostile_model()
    args = {
        _cucumber_unescape(m.group(1))
        for line in render_feature(model).splitlines()
        for m in _CUCUMBER_STRING.finditer(line)
    }
    for key, _sel in collect_targets(model):
        assert key in args, f"registry key {key!r} is not in the feature: {sorted(args)}"
        # And it must need no escaping at all, or the two sides drift again the
        # moment a parser that doesn't unescape (pytest-bdd's parse) reads it.
        assert gherkin_quote(key) == key


def test_no_step_line_carries_a_raw_control_char():
    feature = render_feature(_hostile_model())
    for line in feature.splitlines():
        assert "\t" not in line  # tabs would also fracture a step line


def _pipe_outline_model() -> TestModel:
    """A form-filling case (so it renders as a Scenario Outline with an Examples
    table) whose typed value contains a ``|`` and a newline — the characters that
    corrupt a pipe-delimited table row if unescaped."""
    return TestModel(
        name="PipeFlow",
        app_package="com.example.app",
        cases=[
            TestCase(
                name="pipe",
                description="typed values with pipes do not corrupt the Examples table",
                steps=[
                    Step(ActionType.LAUNCH),
                    Step(
                        ActionType.TYPE,
                        selector=Selector(SelectorStrategy.ID, "query", description="Query"),
                        text="a|b\nc",
                    ),
                    Step(
                        ActionType.TYPE,
                        selector=Selector(SelectorStrategy.ID, "email", description="Email"),
                        text="user@example.com",
                    ),
                ],
            )
        ],
    )


def test_examples_pipe_and_newline_do_not_corrupt_the_table():
    feature = render_feature(_pipe_outline_model())
    # Must be a Scenario Outline with an Examples table.
    assert "Scenario Outline:" in feature and "Examples:" in feature
    # gherkin-official parses the table and unescapes cells; a raw pipe/newline
    # would either fail to parse or split the row into the wrong column count.
    parsed = Parser().parse(TokenScanner(feature))
    examples = parsed["feature"]["children"][0]["scenario"]["examples"][0]
    header = examples["tableHeader"]["cells"]
    rows = examples["tableBody"]
    for row in rows:
        assert len(row["cells"]) == len(header), "Examples row column count drifted from the header"
    # The escaped pipe round-trips to a literal pipe; the newline is neutralised.
    first_col_values = [row["cells"][0]["value"] for row in rows]
    assert "a|b c" in first_col_values, f"pipe/newline value did not survive: {first_col_values}"


def test_examples_cell_quote_stays_escaped_for_the_substituted_step():
    """A cell value is substituted into a *quoted* step argument, so a raw double
    quote there closes the argument early and no Cucumber-expression step matches
    the outline. Gherkin leaves ``\\"`` in the cell, which the {string} parameter
    then unescapes — so the escape must survive the table."""
    model = _pipe_outline_model()
    model.cases[0].steps[1].text = 'say "hi"'
    parsed = Parser().parse(TokenScanner(render_feature(model)))
    examples = parsed["feature"]["children"][0]["scenario"]["examples"][0]
    values = [row["cells"][0]["value"] for row in examples["tableBody"]]
    assert 'say \\"hi\\"' in values, values
    assert _cucumber_unescape('say \\"hi\\"') == 'say "hi"'


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
