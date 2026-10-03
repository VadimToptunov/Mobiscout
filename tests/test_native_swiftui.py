"""SwiftUI from the Swift AST (#317): the Rust core's ``extract_swiftui`` behind
``IOSSourceAnalyzer``, with the regex path as the fallback. The AST path must agree with the
regex path wherever the regex was right, and be right where it guessed. Needs the built
wheel (``maturin develop`` locally; CI's integration job installs it)."""

from pathlib import Path

import pytest

from framework.analyzers import native
from framework.analyzers.ios_source_analyzer import IOSSourceAnalyzer

FIXTURE = Path(__file__).parent / "fixtures" / "source_navigation"

needs_core = pytest.mark.skipif(not native.native_available(), reason="needs the mobiscout_core wheel")


def _analyze(path, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(native, "extract_swiftui", lambda _source: None)  # force the regex path
    return IOSSourceAnalyzer().analyze(str(path))


def _shape(result):
    return {
        "entry": result.entry_screen,
        "screens": [(s.name, s.line_number) for s in result.screens],
        "navigation": [
            (n.from_screen, n.to_screen, n.trigger, n.trigger_test_tag, n.line_number) for n in result.navigation
        ],
        "elements": {e.id: (e.type, e.screen, e.line_number) for e in result.ui_elements},
    }


@needs_core
def test_the_ast_agrees_with_the_regex_path_on_the_navigation_fixture(monkeypatch):
    ast = _shape(_analyze(FIXTURE))
    regex = _shape(_analyze(FIXTURE, monkeypatch))
    # The one deliberate difference: the identifier sits on a NavigationLink, a tap target.
    # The regex path guessed "Text" from the nearest component name in the preceding text.
    assert ast["elements"].pop("open_details") == ("Button", "HomeView", 21)
    assert regex["elements"].pop("open_details") == ("Text", "HomeView", 21)
    assert ast == regex


def _swift(tmp_path, body):
    (tmp_path / "A.swift").write_text(body, encoding="utf-8")
    return tmp_path


@needs_core
def test_an_identifier_in_a_comment_is_not_an_element(tmp_path):
    src = _swift(
        tmp_path,
        """struct A: View {
            // Text("x").accessibilityIdentifier("removed_long_ago")
            var body: some View { Text("y").accessibilityIdentifier("title") }
        }""",
    )
    assert [e.id for e in _analyze(src).ui_elements] == ["title"]


@needs_core
def test_an_interpolated_identifier_is_not_a_locator(tmp_path):
    src = _swift(
        tmp_path,
        """struct A: View {
            var body: some View { ForEach(items) { Text($0.name).accessibilityIdentifier("row_\\($0.id)") } }
        }""",
    )
    assert _analyze(src).ui_elements == []


@needs_core
def test_the_element_type_is_the_view_the_modifier_is_on(tmp_path):
    # The regex path took the nearest component name before the modifier: "Image".
    src = _swift(
        tmp_path,
        """struct A: View {
            var body: some View {
                Button { Image(systemName: "xmark") }.accessibilityIdentifier("close")
            }
        }""",
    )
    (close,) = _analyze(src).ui_elements
    assert close.type == "Button"


@needs_core
def test_a_title_with_a_destination_closure_is_a_link_and_a_value_link_is_not(tmp_path):
    src = _swift(
        tmp_path,
        """struct A: View {
            var body: some View {
                NavigationLink("Help") { HelpView() }
                NavigationLink(value: item) { Text("Row") }
            }
        }""",
    )
    assert [(n.to_screen, n.trigger) for n in _analyze(src).navigation] == [("HelpView", "Help")]


@needs_core
def test_a_file_that_does_not_parse_cleanly_falls_back_to_the_regex_path(tmp_path):
    broken = 'struct A: View {\n var body: some View { Text("t").accessibilityIdentifier("t_id") \n'
    assert native.extract_swiftui(broken) is None
    assert [e.id for e in _analyze(_swift(tmp_path, broken)).ui_elements] == ["t_id"]


def test_without_the_core_the_regex_path_still_analyzes(monkeypatch):
    monkeypatch.setattr(native, "_native_core", lambda: None)
    result = IOSSourceAnalyzer().analyze(str(FIXTURE))
    assert result.entry_screen == "HomeView"
    assert {n.to_screen for n in result.navigation} == {"DetailsView", "ProfileView", "OrdersView", "SettingsView"}
