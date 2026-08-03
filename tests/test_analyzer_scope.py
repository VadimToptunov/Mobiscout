"""Brace-matched scoping: the analyzers attribute an element to the declaration
whose body actually contains it, not a fixed character window / the nearest match
before it (which leaked elements across screen boundaries)."""

import re

from framework.analyzers._scope import block_after, block_text_after, enclosing_declaration

_DECL = re.compile(r"struct\s+(\w+)\s*:\s*View")


def test_block_after_matches_nested_braces():
    src = "struct A: View { var b: some View { Text({ 1 }) } }"
    open_i, close_i = block_after(src, 0)
    assert src[open_i] == "{" and src[close_i] == "}"
    # spans the whole struct body, not the first inner brace
    assert src[open_i : close_i + 1].count("{") == src[open_i : close_i + 1].count("}")
    assert close_i == len(src) - 1


def test_enclosing_declaration_picks_the_containing_view():
    src = "struct First: View { var body: some View { A } }\n" "struct Second: View { var body: some View { B } }\n"
    pos_a = src.index("A")
    pos_b = src.index("B")
    assert enclosing_declaration(src, pos_a, _DECL) == "First"
    assert enclosing_declaration(src, pos_b, _DECL) == "Second"


def test_position_after_a_block_is_not_misattributed():
    src = "struct First: View { var body: some View { A } }\nlet stray = 1\n"
    pos_stray = src.index("stray")
    # Old 'nearest struct before pos' would wrongly say First; brace matching says none.
    assert enclosing_declaration(src, pos_stray, _DECL) is None


def test_block_text_after_returns_the_body():
    src = 'fun Screen() {\n  tag("a")\n}\nfun Other() {\n  tag("b")\n}\n'
    body = block_text_after(src, src.index("fun Screen"))
    assert 'tag("a")' in body and 'tag("b")' not in body  # scoped to Screen, not Other


def test_android_analyzer_scopes_tags_to_their_composable(tmp_path):
    from framework.analyzers.android_analyzer import AndroidAnalyzer

    (tmp_path / "Screens.kt").write_text(
        """
        @Composable
        fun LoginScreen() {
            Button(modifier = Modifier.testTag("login_button")) {}
        }

        @Composable
        fun HomeScreen() {
            Button(modifier = Modifier.testTag("pay_button")) {}
        }
        """,
        encoding="utf-8",
    )
    result = AndroidAnalyzer().analyze(str(tmp_path))
    by_tag = {e.test_tag: e.screen for e in result.ui_elements if e.test_tag}
    # Each tag attributed to its own screen — no cross-boundary leak.
    assert by_tag.get("login_button") == "LoginScreen"
    assert by_tag.get("pay_button") == "HomeScreen"


def test_ios_analyzer_scopes_elements_to_their_view(tmp_path):
    from framework.analyzers.ios_source_analyzer import IOSSourceAnalyzer

    (tmp_path / "Views.swift").write_text(
        """
        struct LoginView: View {
            var body: some View { Button("in") {}.accessibilityIdentifier("login") }
        }
        struct HomeView: View {
            var body: some View { Button("pay") {}.accessibilityIdentifier("pay") }
        }
        """,
        encoding="utf-8",
    )
    result = IOSSourceAnalyzer().analyze(str(tmp_path))
    by_id = {e.id: e.screen for e in result.ui_elements}
    assert by_id.get("login") == "LoginView"
    assert by_id.get("pay") == "HomeView"
