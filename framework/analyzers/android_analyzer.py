"""
Android Static Analyzer

Analyzes Android source code (Kotlin) to extract:
- Compose UI screens
- UI elements with test tags
- Navigation routes
- Retrofit API definitions
"""

import re
from pathlib import Path
from typing import List, Optional

from framework.analyzers._scope import block_text_after, enclosing_declaration
from framework.analyzers.analysis_result import (
    AnalysisResult,
    ScreenCandidate,
    UIElementCandidate,
    NavigationCandidate,
    APIEndpointCandidate,
)


class AndroidAnalyzer:
    """
    Static analyzer for Android/Kotlin projects

    Discovers app structure by parsing source code files.
    Does NOT execute code - only reads and analyzes text.
    """

    def __init__(self) -> None:
        # Patterns for detection
        self.composable_pattern = re.compile(r"@Composable\s+fun\s+(\w+)", re.MULTILINE)
        # Suffix-anchored and case-sensitive: the previous case-insensitive
        # substring form matched "view" inside Preview/Review/Overview, so list
        # rows and debug previews were classified as screens and reached codegen.
        self.screen_pattern = re.compile(r"(?:Screen|Page|View)$")
        self.preview_pattern = re.compile(r"@Preview\b")
        self.test_tag_pattern = re.compile(r'\.testTag\s*\(\s*["\']([^"\']+)["\']\s*\)')
        self.content_desc_pattern = re.compile(r'\.(?:contentDescription|semantics)\s*\(\s*["\']([^"\']+)["\']\s*\)')
        self.nav_route_pattern = re.compile(r"sealed\s+(?:class|object)\s+Screen.*?{", re.DOTALL)
        self.retrofit_pattern = re.compile(r'@(?:GET|POST|PUT|DELETE|PATCH)\s*\(["\']([^"\']+)["\']\)')
        self.retrofit_method_pattern = re.compile(
            r'@(GET|POST|PUT|DELETE|PATCH)\s*\(["\']([^"\']+)["\']\)\s*(?:suspend\s+)?fun\s+(\w+)', re.MULTILINE
        )

    def analyze(self, source_path: str) -> AnalysisResult:
        """
        Analyze Android project source code

        Args:
            source_path: Path to project root or source directory

        Returns:
            AnalysisResult with discovered elements
        """
        source_dir = Path(source_path)

        if not source_dir.exists():
            return AnalysisResult(
                platform="android", source_path=source_path, errors=[f"Source path not found: {source_path}"]
            )

        result = AnalysisResult(platform="android", source_path=source_path)

        # Find all Kotlin files
        kotlin_files = self._find_kotlin_files(source_dir)
        result.files_analyzed = len(kotlin_files)

        # Analyze each file
        for kt_file in kotlin_files:
            try:
                self._analyze_file(kt_file, result)
            except Exception as e:
                result.errors.append(f"Error analyzing {kt_file}: {e}")

        # Post-process results
        self._link_elements_to_screens(result)

        return result

    def _find_kotlin_files(self, source_dir: Path) -> List[Path]:
        """Find all .kt files in directory"""
        return list(source_dir.rglob("*.kt"))

    def _analyze_file(self, file_path: Path, result: AnalysisResult) -> None:
        """Analyze single Kotlin file"""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            result.warnings.append(f"Could not read {file_path}: {e}")
            return

        lines = content.split("\n")

        # Detect screens (Composable functions that look like screens)
        self._detect_screens(content, file_path, lines, result)

        # Detect UI elements (with test tags)
        self._detect_ui_elements(content, file_path, lines, result)

        # Detect navigation
        self._detect_navigation(content, file_path, lines, result)

        # Detect API endpoints (Retrofit)
        if "interface" in content and any(x in content for x in ["@GET", "@POST", "@PUT", "@DELETE"]):
            self._detect_api_endpoints(content, file_path, lines, result)

    def _detect_screens(self, content: str, file_path: Path, lines: List[str], result: AnalysisResult) -> None:
        """Detect Composable screen functions"""
        for match in self.composable_pattern.finditer(content):
            func_name = match.group(1)

            # Check if it looks like a screen
            if not self.screen_pattern.search(func_name):
                continue

            # @Preview composables are debug-only and have no runtime route, so
            # generating page objects and smoke cases for them produces tests the
            # app can never navigate to.
            if self._is_preview(content, match.start()):
                continue

            line_num = content[: match.start()].count("\n") + 1

            # Try to extract route if present
            route = self._extract_route_for_screen(content, func_name)

            # Try to find UI elements in this screen
            ui_elements = self._find_ui_elements_in_scope(content, match.start(), func_name)

            screen = ScreenCandidate(
                name=func_name,
                file_path=str(file_path),
                line_number=line_num,
                composable_name=func_name,
                route=route,
                ui_elements=ui_elements,
            )

            result.screens.append(screen)

    def _is_preview(self, content: str, composable_pos: int) -> bool:
        """Whether the composable at ``composable_pos`` is annotated @Preview.

        Annotations sit directly above the @Composable, separated only by other
        annotations and blank lines, so scanning back until the first non-annotation
        line is enough — except that an annotation's argument list may itself span
        several lines::

            @Preview(
                showBackground = true,
            )
            @Composable
            fun PreviewSettingsPage() { ... }

        Scanning back naively stops at the lone ``)`` (it doesn't start with ``@``) and
        the @Preview is never seen, so a debug-only preview reaches codegen as a real
        screen. Track parenthesis depth while walking up so a wrapped annotation is read
        as the single annotation it is.
        """
        depth = 0  # unclosed ")" seen while walking upward = inside an argument list
        for line in reversed(content[:composable_pos].splitlines()):
            stripped = line.strip()
            if not stripped:
                continue
            closers, openers = stripped.count(")"), stripped.count("(")
            if depth > 0:
                depth += closers - openers
                if depth > 0:
                    continue  # still inside the argument list
                depth = 0  # this line opened it — it's the annotation itself
                if not stripped.startswith("@"):
                    return False
                if self.preview_pattern.match(stripped):
                    return True
                continue
            if not stripped.startswith("@"):
                if closers > openers:
                    depth = closers - openers  # the tail of a multi-line annotation
                    continue
                return False
            if self.preview_pattern.match(stripped):
                return True

        return False

    def _detect_ui_elements(self, content: str, file_path: Path, lines: List[str], result: AnalysisResult) -> None:
        """Detect UI elements with test tags or content descriptions"""

        # Find test tags
        for match in self.test_tag_pattern.finditer(content):
            test_tag = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            # Try to determine element type from context
            element_type = self._guess_element_type(content, match.start())

            # Try to find which screen this belongs to
            screen_name = self._find_containing_screen(content, match.start())

            element = UIElementCandidate(
                id=test_tag,
                type=element_type or "Unknown",
                screen=screen_name,
                file_path=str(file_path),
                line_number=line_num,
                test_tag=test_tag,
            )

            result.ui_elements.append(element)

        # Find content descriptions
        for match in self.content_desc_pattern.finditer(content):
            content_desc = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            element_type = self._guess_element_type(content, match.start())
            screen_name = self._find_containing_screen(content, match.start())

            element = UIElementCandidate(
                id=content_desc.lower().replace(" ", "_"),
                type=element_type or "Unknown",
                screen=screen_name,
                file_path=str(file_path),
                line_number=line_num,
                content_description=content_desc,
            )

            result.ui_elements.append(element)

    def _detect_navigation(self, content: str, file_path: Path, lines: List[str], result: AnalysisResult) -> None:
        """Detect navigation routes and transitions"""

        # Look for navigation calls: navController.navigate("route")
        nav_pattern = re.compile(r'navigate\s*\(\s*["\']([^"\']+)["\']\s*\)')

        for match in nav_pattern.finditer(content):
            route = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            # Try to find which screen this is called from
            from_screen = self._find_containing_screen(content, match.start())

            navigation = NavigationCandidate(
                from_screen=from_screen, to_screen=route, route=route, file_path=str(file_path), line_number=line_num
            )

            result.navigation.append(navigation)

        # Look for sealed class Screen definitions
        screen_def_pattern = re.compile(
            r'(?:object|data class)\s+(\w+)\s*[:(].*?route\s*=\s*["\']([^"\']+)["\']', re.MULTILINE
        )

        for match in screen_def_pattern.finditer(content):
            screen_name = match.group(1)
            route = match.group(2)
            line_num = content[: match.start()].count("\n") + 1

            navigation = NavigationCandidate(
                from_screen=None, to_screen=screen_name, route=route, file_path=str(file_path), line_number=line_num
            )

            result.navigation.append(navigation)

    def _detect_api_endpoints(self, content: str, file_path: Path, lines: List[str], result: AnalysisResult) -> None:
        """Detect Retrofit API endpoints"""

        # Extract interface name
        interface_match = re.search(r"interface\s+(\w+)", content)
        interface_name = interface_match.group(1) if interface_match else "Unknown"

        # Find all API methods
        for match in self.retrofit_method_pattern.finditer(content):
            http_method = match.group(1)
            path = match.group(2)
            func_name = match.group(3)
            line_num = content[: match.start()].count("\n") + 1

            # Try to extract request/response types
            func_signature = self._extract_function_signature(content, match.end())
            request_type, response_type = self._parse_function_signature(func_signature)

            endpoint = APIEndpointCandidate(
                method=http_method,
                path=path,
                interface_name=interface_name,
                function_name=func_name,
                request_type=request_type,
                response_type=response_type,
                file_path=str(file_path),
                line_number=line_num,
            )

            result.api_endpoints.append(endpoint)

    def _extract_route_for_screen(self, content: str, screen_name: str) -> Optional[str]:
        """Try to find route definition for a screen"""
        # Look for: Screen.ScreenName.route or similar
        pattern = re.compile(rf'Screen\.{screen_name}.*?route\s*=\s*["\']([^"\']+)["\']')
        match = pattern.search(content)
        if match:
            return match.group(1)
        return None

    def _find_ui_elements_in_scope(self, content: str, start_pos: int, func_name: str) -> List[str]:
        """Find test tags within a Composable's actual ``{...}`` body (brace-matched,
        so tags from the *next* function no longer leak into this one)."""
        scope = block_text_after(content, start_pos) or content[start_pos : start_pos + 2000]
        return [match.group(1) for match in self.test_tag_pattern.finditer(scope)]

    def _guess_element_type(self, content: str, position: int) -> Optional[str]:
        """Guess UI element type from surrounding code"""
        # Look backwards for element type
        context = content[max(0, position - 200) : position]

        if "Button" in context:
            return "Button"
        elif "TextField" in context or "OutlinedTextField" in context:
            return "TextField"
        elif "Text(" in context:
            return "Text"
        elif "Image" in context:
            return "Image"
        elif "Icon" in context:
            return "Icon"

        return None

    def _find_containing_screen(self, content: str, position: int) -> Optional[str]:
        """The @Composable screen function whose body actually contains this
        position (brace-matched), not merely the nearest one before it."""
        func_name = enclosing_declaration(content, position, self.composable_pattern)
        if func_name and self.screen_pattern.search(func_name):
            return func_name
        return None

    def _extract_function_signature(self, content: str, start_pos: int) -> str:
        """Extract function signature after method annotation"""
        # Get next ~200 characters
        signature = content[start_pos : start_pos + 200]

        # Find closing parenthesis of function
        paren_count = 0
        for i, char in enumerate(signature):
            if char == "(":
                paren_count += 1
            elif char == ")":
                paren_count -= 1
                if paren_count == 0:
                    return signature[: i + 1]

        return signature

    def _parse_function_signature(self, signature: str) -> tuple[Optional[str], Optional[str]]:
        """Parse request and response types from function signature"""
        # Very simplified parsing
        request_type = None
        response_type = None

        # Look for @Body parameter
        body_match = re.search(r"@Body\s+\w+:\s*(\w+)", signature)
        if body_match:
            request_type = body_match.group(1)

        # Look for return type
        return_match = re.search(r":\s*(?:Response<)?(\w+)>?", signature)
        if return_match:
            response_type = return_match.group(1)

        return request_type, response_type

    def _link_elements_to_screens(self, result: AnalysisResult) -> None:
        """Post-process to link orphan elements to their screens"""
        # Build screen name index
        screen_names = {s.name for s in result.screens}

        for element in result.ui_elements:
            if not element.screen:
                # Try to guess from file path
                for screen_name in screen_names:
                    if screen_name.lower() in element.file_path.lower():
                        element.screen = screen_name
                        break
