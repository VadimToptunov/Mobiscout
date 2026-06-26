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

from framework.analyzers.analysis_result import (
    AnalysisResult,
    ScreenCandidate,
    UIElementCandidate,
    NavigationCandidate,
    APIEndpointCandidate
)


class AndroidAnalyzer:
    """
    Static analyzer for Android/Kotlin projects

    Discovers app structure by parsing source code files.
    Does NOT execute code - only reads and analyzes text.
    """

    def __init__(self) -> None:
        # Patterns for detection
        self.composable_pattern = re.compile(r'@Composable\s+fun\s+(\w+)', re.MULTILINE)
        self.screen_pattern = re.compile(r'(?:Screen|Page|View)\w*', re.IGNORECASE)
        self.test_tag_pattern = re.compile(r'\.testTag\s*\(\s*["\']([^"\']+)["\']\s*\)')
        self.content_desc_pattern = re.compile(
            r'\.(?:contentDescription|semantics)\s*\(\s*["\']([^"\']+)["\']\s*\)'
        )
        self.nav_route_pattern = re.compile(r'sealed\s+(?:class|object)\s+Screen.*?{', re.DOTALL)
        self.retrofit_pattern = re.compile(r'@(?:GET|POST|PUT|DELETE|PATCH)\s*\(["\']([^"\']+)["\']\)')
        self.retrofit_method_pattern = re.compile(
            r'@(GET|POST|PUT|DELETE|PATCH)\s*\(["\']([^"\']+)["\']\)\s*(?:suspend\s+)?fun\s+(\w+)',
            re.MULTILINE
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
                platform="android",
                source_path=source_path,
                errors=[f"Source path not found: {source_path}"]
            )

        result = AnalysisResult(
            platform="android",
            source_path=source_path
        )

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
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            result.warnings.append(f"Could not read {file_path}: {e}")
            return

        lines = content.split('\n')

        # Detect screens (Composable functions that look like screens)
        self._detect_screens(content, file_path, lines, result)

        # Detect UI elements (with test tags)
        self._detect_ui_elements(content, file_path, lines, result)

        # Detect navigation
        self._detect_navigation(content, file_path, lines, result)

        # Detect API endpoints (Retrofit)
        if 'interface' in content and any(x in content for x in ['@GET', '@POST', '@PUT', '@DELETE']):
            self._detect_api_endpoints(content, file_path, lines, result)

    def _detect_screens(
            self,
            content: str,
            file_path: Path,
            lines: List[str],
            result: AnalysisResult
    ) -> None:
        """Detect Composable screen functions"""
        for match in self.composable_pattern.finditer(content):
            func_name = match.group(1)

            # Check if it looks like a screen
            if not self.screen_pattern.search(func_name):
                continue

            line_num = content[:match.start()].count('\n') + 1

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
                ui_elements=ui_elements
            )

            result.screens.append(screen)

    def _detect_ui_elements(
            self,
            content: str,
            file_path: Path,
            lines: List[str],
            result: AnalysisResult
    ) -> None:
        """Detect UI elements with test tags or content descriptions"""

        # Find test tags
        for match in self.test_tag_pattern.finditer(content):
            test_tag = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

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
                test_tag=test_tag
            )

            result.ui_elements.append(element)

        # Find content descriptions
        for match in self.content_desc_pattern.finditer(content):
            content_desc = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            element_type = self._guess_element_type(content, match.start())
            screen_name = self._find_containing_screen(content, match.start())

            element = UIElementCandidate(
                id=content_desc.lower().replace(' ', '_'),
                type=element_type or "Unknown",
                screen=screen_name,
                file_path=str(file_path),
                line_number=line_num,
                content_description=content_desc
            )

            result.ui_elements.append(element)

    def _detect_navigation(
            self,
            content: str,
            file_path: Path,
            lines: List[str],
            result: AnalysisResult
    ) -> None:
        """Detect navigation routes and transitions"""

        # Look for navigation calls: navController.navigate("route")
        nav_pattern = re.compile(r'navigate\s*\(\s*["\']([^"\']+)["\']\s*\)')

        for match in nav_pattern.finditer(content):
            route = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Try to find which screen this is called from
            from_screen = self._find_containing_screen(content, match.start())

            navigation = NavigationCandidate(
                from_screen=from_screen,
                to_screen=route,
                route=route,
                file_path=str(file_path),
                line_number=line_num
            )

            result.navigation.append(navigation)

        # Look for sealed class Screen definitions
        screen_def_pattern = re.compile(
            r'(?:object|data class)\s+(\w+)\s*[:(].*?route\s*=\s*["\']([^"\']+)["\']',
            re.MULTILINE
        )

        for match in screen_def_pattern.finditer(content):
            screen_name = match.group(1)
            route = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            navigation = NavigationCandidate(
                from_screen=None,
                to_screen=screen_name,
                route=route,
                file_path=str(file_path),
                line_number=line_num
            )

            result.navigation.append(navigation)

    def _detect_api_endpoints(
            self,
            content: str,
            file_path: Path,
            lines: List[str],
            result: AnalysisResult
    ) -> None:
        """Detect Retrofit API endpoints"""

        # Extract interface name
        interface_match = re.search(r'interface\s+(\w+)', content)
        interface_name = interface_match.group(1) if interface_match else "Unknown"

        # Find all API methods
        for match in self.retrofit_method_pattern.finditer(content):
            http_method = match.group(1)
            path = match.group(2)
            func_name = match.group(3)
            line_num = content[:match.start()].count('\n') + 1

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
                line_number=line_num
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

    def _find_ui_elements_in_scope(
            self,
            content: str,
            start_pos: int,
            func_name: str
    ) -> List[str]:
        """Find test tags within a function scope"""
        # Simple heuristic: look for test tags within ~500 characters of function start
        scope = content[start_pos:start_pos + 2000]

        tags = []
        for match in self.test_tag_pattern.finditer(scope):
            tags.append(match.group(1))

        return tags

    def _guess_element_type(self, content: str, position: int) -> Optional[str]:
        """Guess UI element type from surrounding code"""
        # Look backwards for element type
        context = content[max(0, position - 200):position]

        if 'Button' in context:
            return 'Button'
        elif 'TextField' in context or 'OutlinedTextField' in context:
            return 'TextField'
        elif 'Text(' in context:
            return 'Text'
        elif 'Image' in context:
            return 'Image'
        elif 'Icon' in context:
            return 'Icon'

        return None

    def _find_containing_screen(self, content: str, position: int) -> Optional[str]:
        """Find which @Composable screen function contains this position"""
        # Look backwards for @Composable function
        before = content[:position]

        # Find all @Composable functions before this point
        composables = list(self.composable_pattern.finditer(before))

        if composables:
            last_composable = composables[-1]
            func_name = last_composable.group(1)

            # Check if it looks like a screen
            if self.screen_pattern.search(func_name):
                return func_name

        return None

    def _extract_function_signature(self, content: str, start_pos: int) -> str:
        """Extract function signature after method annotation"""
        # Get next ~200 characters
        signature = content[start_pos:start_pos + 200]

        # Find closing parenthesis of function
        paren_count = 0
        for i, char in enumerate(signature):
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
                if paren_count == 0:
                    return signature[:i + 1]

        return signature

    def _parse_function_signature(self, signature: str) -> tuple[Optional[str], Optional[str]]:
        """Parse request and response types from function signature"""
        # Very simplified parsing
        request_type = None
        response_type = None

        # Look for @Body parameter
        body_match = re.search(r'@Body\s+\w+:\s*(\w+)', signature)
        if body_match:
            request_type = body_match.group(1)

        # Look for return type
        return_match = re.search(r':\s*(?:Response<)?(\w+)>?', signature)
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
