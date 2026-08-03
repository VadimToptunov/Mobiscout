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
from typing import List, Optional

from framework.analyzers._scope import enclosing_declaration
from framework.analyzers.analysis_result import AnalysisResult, ScreenCandidate, UIElementCandidate

# A struct conforming to View — a SwiftUI screen/view.
_VIEW = re.compile(r"struct\s+(\w+)\s*:\s*(?:some\s+)?View\b")
# The reliable locator: .accessibilityIdentifier("id") (Appium iOS matches it).
_A11Y_ID = re.compile(r"\.accessibilityIdentifier\(\s*[\"']([^\"']+)[\"']\s*\)")
# accessibilityLabel("...") — also queryable, used when no identifier is present.
_A11Y_LABEL = re.compile(r"\.accessibilityLabel\(\s*[\"']([^\"']+)[\"']\s*\)")

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
