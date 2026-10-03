"""Static analysis of SwiftUI source into an ``AnalysisResult``.

The iOS counterpart of :class:`AndroidAnalyzer`: it discovers **screens** (structs
conforming to ``View``) and **UI elements** (components carrying an
``accessibilityIdentifier`` / ``accessibilityLabel``) so the same source → UI-test
bridge (``analysis_to_app_model`` → ``build_smoke_model`` → emitters) that works
for Android/Compose also works for iOS/SwiftUI.

Regex/heuristic like the Android analyzer — good enough to map the a11y-identified
elements the tests need to locate; a full Swift AST is a separate, larger effort.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from framework.analyzers._scope import block_after, enclosing_declaration, paren_close
from framework.analyzers.analysis_result import (
    AnalysisResult,
    NavigationCandidate,
    ScreenCandidate,
    UIElementCandidate,
)

# A struct conforming to View — a SwiftUI screen/view.
_VIEW = re.compile(r"struct\s+(\w+)\s*:\s*(?:some\s+)?View\b")
# The reliable locator: .accessibilityIdentifier("id") (Appium iOS matches it).
_A11Y_ID = re.compile(r"\.accessibilityIdentifier\(\s*[\"']([^\"']+)[\"']\s*\)")
# accessibilityLabel("...") — also queryable, used when no identifier is present.
_A11Y_LABEL = re.compile(r"\.accessibilityLabel\(\s*[\"']([^\"']+)[\"']\s*\)")

# Where the app opens: @main struct X: App { ... WindowGroup { ContentView() } }.
_WINDOW_GROUP_ROOT = re.compile(r"WindowGroup\s*\{\s*(\w+)\s*\(")
# NavigationLink in its three forms: (destination:) { label }, ("Label", destination:),
# and { destination } label: { label }.
_NAV_LINK = re.compile(r"\bNavigationLink\s*([({])")
_DESTINATION = re.compile(r"destination\s*:\s*\{?\s*(\w+)\s*\(")
_FIRST_VIEW = re.compile(r"^\s*\{?\s*(\w+)\s*\(")
_STRING_ARG = re.compile(r'^\s*"([^"]+)"')
_TEXT = re.compile(r'\bText\s*\(\s*"([^"]+)"')
_LABEL = re.compile(r"\blabel\s*:\s*\{")
# A presented screen: .sheet(...) { SettingsView() } / .fullScreenCover(...) { ... }.
_PRESENTED = re.compile(r"\.(?:sheet|fullScreenCover)\s*\(")
# The modifier chain right after a view: each line starting with ".".
_MODIFIERS = re.compile(r"\A(?:\s*\.[^\n]*)+")

# SwiftUI component keyword -> UIElementCandidate.type (mapped to ElementType later).
_COMPONENTS = ("Button", "SecureField", "TextField", "TextEditor", "Text", "Image", "Toggle", "Picker", "List")


class IOSSourceAnalyzer:
    """Extract screens + a11y-identified UI elements from a SwiftUI source tree."""

    def analyze(self, source_path: str) -> AnalysisResult:
        """Walk ``*.swift`` under ``source_path`` and return the discovered screens
        and UI elements (never raises; unreadable files are recorded as warnings)."""
        root = Path(source_path)
        result = AnalysisResult(platform="ios", source_path=source_path)
        if not root.exists():
            result.errors.append(f"Source path not found: {source_path}")
            return result

        for swift in sorted(root.rglob("*.swift")):
            try:
                content = swift.read_text(encoding="utf-8")
            except OSError as exc:
                result.warnings.append(f"Could not read {swift}: {exc}")
                continue
            self._analyze_file(content, swift, result)
            result.files_analyzed += 1
        return result

    def _analyze_file(self, content: str, path: Path, result: AnalysisResult) -> None:
        root = _WINDOW_GROUP_ROOT.search(content)
        if root and result.entry_screen is None:
            result.entry_screen = root.group(1)
        self._detect_navigation(content, path, result)
        for match in _VIEW.finditer(content):
            result.screens.append(
                ScreenCandidate(
                    name=match.group(1),
                    file_path=str(path),
                    line_number=content[: match.start()].count("\n") + 1,
                )
            )

        # An element is worth a test when it carries an accessibility identifier
        # (preferred) or label — that is exactly what a UI test locates it by.
        seen: set = set()
        for pattern, is_identifier in ((_A11Y_ID, True), (_A11Y_LABEL, False)):
            for match in pattern.finditer(content):
                value = match.group(1)
                if value in seen:
                    continue
                seen.add(value)
                result.ui_elements.append(
                    UIElementCandidate(
                        id=value,
                        type=self._guess_type(content, match.start()),
                        screen=self._containing_view(content, match.start()),
                        file_path=str(path),
                        line_number=content[: match.start()].count("\n") + 1,
                        # Both an identifier and a label are matched on iOS as the
                        # accessibility id — carry either as the element's a11y name.
                        content_description=value,
                    )
                )

    def _detect_navigation(self, content: str, path: Path, result: AnalysisResult) -> None:
        """One NavigationCandidate per NavigationLink (with the link's label text and its
        accessibilityIdentifier, the tap target) and per .sheet / .fullScreenCover (its
        trigger is a separate Button flipping a binding, so none is recorded)."""
        for match in _NAV_LINK.finditer(content):
            destination, label, end = _nav_link(content, match)
            if destination is None:
                continue
            self._add_edge(content, path, result, match.start(), destination, label, _identifier_after(content, end))
        for match in _PRESENTED.finditer(content):
            body = block_after(content, paren_close(content, match.end() - 1))
            view = _FIRST_VIEW.match(content[body[0] + 1 : body[1]]) if body else None
            if view:
                self._add_edge(content, path, result, match.start(), view.group(1), None, None)

    @staticmethod
    def _add_edge(
        content: str,
        path: Path,
        result: AnalysisResult,
        pos: int,
        destination: str,
        trigger: Optional[str],
        trigger_tag: Optional[str],
    ) -> None:
        result.navigation.append(
            NavigationCandidate(
                from_screen=enclosing_declaration(content, pos, _VIEW),
                to_screen=destination,
                route=destination,
                trigger=trigger,
                trigger_test_tag=trigger_tag,
                file_path=str(path),
                line_number=content[:pos].count("\n") + 1,
            )
        )

    @staticmethod
    def _guess_type(content: str, pos: int) -> str:
        """The SwiftUI component the modifier is attached to — scan back a small
        window for the nearest component keyword (defaults to 'Text')."""
        window = content[max(0, pos - 400) : pos]
        best_type, best_at = "Text", -1
        for component in _COMPONENTS:
            at = window.rfind(component)
            if at > best_at:
                best_type, best_at = component, at
        return best_type

    @staticmethod
    def _containing_view(content: str, pos: int) -> Optional[str]:
        """The ``struct X: View`` whose body actually contains the element (brace-
        matched, so an element after a view's closing brace isn't misattributed)."""
        return enclosing_declaration(content, pos, _VIEW)


def _nav_link(content: str, match: "re.Match[str]") -> Tuple[Optional[str], Optional[str], int]:
    """(destination view, label text, end of the link) for the NavigationLink at ``match``."""
    if match.group(1) == "(":
        args_end = paren_close(content, match.end() - 1)
        args = content[match.end() : args_end]
        destination = _DESTINATION.search(args)
        label = _STRING_ARG.match(args)
        end = args_end + 1
        trailing = block_after(content, end)
        if trailing and not content[end : trailing[0]].strip():  # NavigationLink(destination:) { Text("x") }
            if label is None:
                label = _TEXT.search(content[trailing[0] : trailing[1]])
            end = trailing[1] + 1
        return (destination.group(1) if destination else None), (label.group(1) if label else None), end
    # NavigationLink { DetailView() } label: { Text("Details") }
    dest_block = block_after(content, match.end() - 1)
    if dest_block is None:
        return None, None, match.end()
    view = _FIRST_VIEW.match(content[dest_block[0] + 1 : dest_block[1]])
    label_kw = _LABEL.match(content, dest_block[1] + 1) or _LABEL.search(content, dest_block[1] + 1, dest_block[1] + 40)
    end = dest_block[1] + 1
    label = None
    if label_kw:
        label_block = block_after(content, label_kw.end() - 1)
        if label_block:
            label = _TEXT.search(content[label_block[0] : label_block[1]])
            end = label_block[1] + 1
    return (view.group(1) if view else None), (label.group(1) if label else None), end


def _identifier_after(content: str, end: int) -> Optional[str]:
    """The accessibilityIdentifier in the modifier chain right after a view ending at ``end``."""
    chain = _MODIFIERS.match(content[end:])
    ident = _A11Y_ID.search(chain.group(0)) if chain else None
    return ident.group(1) if ident else None
