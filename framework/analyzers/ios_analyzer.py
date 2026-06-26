"""
iOS Static Analyzer

Analyzes Swift/SwiftUI source code to extract:
- SwiftUI View definitions (screens)
- UI elements with accessibility identifiers
- Navigation routes
- API endpoint definitions
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .analysis_result import (
    AnalysisResult,
    ScreenCandidate,
    UIElementCandidate,
    APIEndpointCandidate,
    NavigationCandidate,
)


@dataclass
class IOSAnalyzer:
    """
    Static analyzer for iOS (Swift/SwiftUI) projects
    """

    project_path: Path
    source_dirs: List[Path] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize analyzer with default source directories"""
        if not self.source_dirs:
            # Default Swift source locations
            potential_dirs = [
                self.project_path / "Sources",
                self.project_path / "App",
                self.project_path / "Views",
                self.project_path / "Screens",
            ]
            self.source_dirs = [d for d in potential_dirs if d.exists()]

            # If no standard dirs, search recursively for .swift files
            if not self.source_dirs:
                self.source_dirs = [self.project_path]

    def analyze(self) -> AnalysisResult:
        """
        Analyze iOS project and extract static information

        Returns:
            AnalysisResult with discovered screens, elements, APIs, and navigation
        """
        print(f"[IOSAnalyzer] Analyzing project: {self.project_path}")

        screens: List[ScreenCandidate] = []
        elements: List[UIElementCandidate] = []
        apis: List[APIEndpointCandidate] = []
        navigation: List[NavigationCandidate] = []

        # Find all Swift files
        swift_files = self._find_swift_files()
        print(f"[IOSAnalyzer] Found {len(swift_files)} Swift files")

        # Analyze each file
        for swift_file in swift_files:
            try:
                file_screens, file_elements = self._analyze_views_file(swift_file)
                screens.extend(file_screens)
                elements.extend(file_elements)

                file_nav = self._analyze_navigation_file(swift_file)
                navigation.extend(file_nav)

                file_apis = self._analyze_api_file(swift_file)
                apis.extend(file_apis)

            except Exception as e:
                print(f"[IOSAnalyzer] Error analyzing {swift_file.name}: {e}")
                continue

        print(
            f"[IOSAnalyzer] Found {len(screens)} screens, {len(elements)} elements, "
            f"{len(apis)} APIs, {len(navigation)} navigation routes"
        )

        return AnalysisResult(
            platform="ios",
            source_path=str(self.project_path),
            screens=screens,
            ui_elements=elements,
            api_endpoints=apis,
            navigation=navigation,
            files_analyzed=len(swift_files),
            metadata={"project_path": str(self.project_path)},
        )

    def _find_swift_files(self) -> List[Path]:
        """Find all .swift files in source directories"""
        swift_files = []

        for source_dir in self.source_dirs:
            for root, _, files in os.walk(source_dir):
                for file in files:
                    if file.endswith(".swift"):
                        swift_files.append(Path(root) / file)

        return swift_files

    def _analyze_views_file(self, file_path: Path) -> tuple[List[ScreenCandidate], List[UIElementCandidate]]:
        """
        Analyze a Swift file for SwiftUI View definitions

        Returns:
            Tuple of (screens, elements)
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        screens = []
        elements = []

        # Pattern: struct SomeView: View {
        view_pattern = r"struct\s+(\w+View)\s*:\s*View\s*\{"

        for match in re.finditer(view_pattern, content):
            view_name = match.group(1)

            # Extract view body
            start_pos = match.end()
            body_content = self._extract_balanced_braces(content, start_pos)

            # Check if this is a screen (has navigationTitle or is a primary view)
            is_screen = (
                    "navigationTitle" in body_content
                    or "NavigationView" in body_content
                    or "TabView" in body_content
                    or view_name
                    in ["ContentView", "OnboardingView", "LoginView", "HomeView", "KYCView", "TopUpView",
                        "SendMoneyView"]
            )

            if is_screen:
                screens.append(
                    ScreenCandidate(
                        name=view_name,
                        file_path=str(file_path.relative_to(self.project_path)),
                        line_number=content[: match.start()].count("\n") + 1,
                        route=self._infer_route_from_view_name(view_name),
                        composable_name=view_name,
                        parameters=[],
                    )
                )

                # Extract elements from this screen
                screen_elements = self._extract_elements_from_view(
                    screen_name=view_name, full_content=content, view_body_start=start_pos, file_path=file_path
                )
                elements.extend(screen_elements)

        return screens, elements

    def _extract_elements_from_view(
            self, screen_name: str, full_content: str, view_body_start: int, file_path: Path
    ) -> List[UIElementCandidate]:
        """Extract UI elements with accessibility identifiers from view"""
        elements = []

        # Pattern: .accessibilityIdentifier("any_string_including_interpolation")
        # Uses greedy matching to capture everything between outer quotes,
        # including Swift string interpolation \(...) with nested quotes
        accessibility_pattern = r'\.accessibilityIdentifier\("(.+)"\)'

        # Search in the full content starting from view body
        for match in re.finditer(accessibility_pattern, full_content[view_body_start:]):
            # Get the captured identifier (may contain \(...) for string interpolation)
            element_id = match.group(1)

            # Calculate absolute position in file
            absolute_pos = view_body_start + match.start()

            # Try to infer element type from context
            context_start = max(0, absolute_pos - 200)
            context = full_content[context_start:absolute_pos]

            element_type = self._infer_element_type_from_context(context)

            # Calculate line number from file start
            line_number = full_content[:absolute_pos].count("\n") + 1

            elements.append(
                UIElementCandidate(
                    id=element_id,
                    type=element_type,
                    screen=screen_name,
                    file_path=str(file_path.relative_to(self.project_path)),
                    line_number=line_number,
                    test_tag=element_id,  # Use accessibility ID as test tag
                )
            )

        return elements

    def _infer_element_type_from_context(self, context: str) -> str:
        """Infer element type from surrounding code"""
        context_lower = context.lower()

        if "button" in context_lower:
            return "Button"
        elif "textfield" in context_lower:
            return "TextField"
        elif "securefield" in context_lower:
            return "SecureField"
        elif "text(" in context_lower:
            return "Text"
        elif "image" in context_lower:
            return "Image"
        elif "picker" in context_lower:
            return "Picker"
        elif "toggle" in context_lower:
            return "Toggle"
        elif "slider" in context_lower:
            return "Slider"
        elif "list" in context_lower or "scrollview" in context_lower:
            return "List"
        else:
            return "View"

    def _analyze_navigation_file(self, file_path: Path) -> List[NavigationCandidate]:
        """Analyze navigation routes from Swift file"""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        navigation = []

        # Pattern: .sheet(isPresented: ...) or .fullScreenCover
        sheet_pattern = r"\.(sheet|fullScreenCover)\(isPresented:[^{]+\{\s*(\w+View)\("

        for match in re.finditer(sheet_pattern, content):
            presentation_type = match.group(1)
            destination_view = match.group(2)

            # Calculate line number
            line_number = content[: match.start()].count("\n") + 1

            navigation.append(
                NavigationCandidate(
                    from_screen="Unknown",  # Would need more context
                    to_screen=destination_view,
                    route=self._infer_route_from_view_name(destination_view),
                    trigger=f"{presentation_type}_presentation",
                    file_path=str(file_path.relative_to(self.project_path)),
                    line_number=line_number,
                )
            )

        # Pattern: NavigationLink(destination: SomeView())
        navlink_pattern = r"NavigationLink\([^)]*destination:\s*(\w+View)\("

        for match in re.finditer(navlink_pattern, content):
            destination_view = match.group(1)

            # Calculate line number
            line_number = content[: match.start()].count("\n") + 1

            navigation.append(
                NavigationCandidate(
                    from_screen="Unknown",
                    to_screen=destination_view,
                    route=self._infer_route_from_view_name(destination_view),
                    trigger="navigation_link",
                    file_path=str(file_path.relative_to(self.project_path)),
                    line_number=line_number,
                )
            )

        return navigation

    def _analyze_api_file(self, file_path: Path) -> List[APIEndpointCandidate]:
        """Analyze API endpoint definitions from Swift file"""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        apis = []

        # Pattern: let url = URL(string: "https://api.example.com/endpoint")
        url_pattern = r'URL\(string:\s*"(https?://[^"]+)"\)'

        for match in re.finditer(url_pattern, content):
            url = match.group(1)

            # Try to extract method from surrounding context
            context_start = max(0, match.start() - 300)
            context_end = min(len(content), match.end() + 300)
            context = content[context_start:context_end]

            method = self._extract_http_method_from_context(context)

            # Calculate line number
            line_number = content[: match.start()].count("\n") + 1

            apis.append(
                APIEndpointCandidate(
                    method=method,
                    path=self._extract_path_from_url(url),
                    interface_name="URLSession",  # Generic for iOS
                    function_name=f"{method.lower()}_request",
                    file_path=str(file_path.relative_to(self.project_path)),
                    line_number=line_number,
                )
            )

        # Pattern: URLRequest with httpMethod
        request_pattern = (
            r'var\s+request\s*=\s*URLRequest\(url:[^)]+\)[^}]*?\.httpMethod\s*=\s*"(GET|POST|PUT|DELETE|PATCH)"'
        )

        for match in re.finditer(request_pattern, content, re.DOTALL):
            method = match.group(1)
            # URL would be captured separately

        return apis

    def _extract_http_method_from_context(self, context: str) -> str:
        """Extract HTTP method from surrounding code"""
        method_match = re.search(r'httpMethod\s*=\s*"(GET|POST|PUT|DELETE|PATCH)"', context)
        if method_match:
            return method_match.group(1)

        # Check for method in URLSession.dataTask or similar
        if "POST" in context.upper():
            return "POST"
        elif "PUT" in context.upper():
            return "PUT"
        elif "DELETE" in context.upper():
            return "DELETE"
        elif "PATCH" in context.upper():
            return "PATCH"

        return "GET"  # Default

    def _extract_path_from_url(self, url: str) -> str:
        """Extract path from full URL"""
        # Remove protocol and domain
        match = re.search(r"https?://[^/]+(/.+)", url)
        if match:
            return match.group(1)
        return url

    def _infer_service_name_from_url(self, url: str) -> str:
        """Infer service name from URL"""
        # Extract domain
        match = re.search(r"https?://([^/]+)", url)
        if match:
            domain = match.group(1)
            # Remove common prefixes
            domain = re.sub(r"^(api\.|www\.)", "", domain)
            # Remove TLD
            domain = re.sub(r"\.(com|net|org|io)$", "", domain)
            return domain.replace(".", "_")
        return "unknown"

    def _infer_route_from_view_name(self, view_name: str) -> str:
        """Infer navigation route from view name"""
        # Remove 'View' suffix and convert to snake_case
        route = view_name.replace("View", "")
        route = re.sub(r"([A-Z])", r"_\1", route).lower().strip("_")
        return f"/{route}"

    def _extract_balanced_braces(self, content: str, start_pos: int) -> str:
        """Extract content within balanced braces"""
        depth = 0
        result = []

        for i in range(start_pos, len(content)):
            char = content[i]
            result.append(char)

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break

        return "".join(result)
