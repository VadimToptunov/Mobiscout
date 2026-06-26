"""
iOS Business Logic Analyzer

Extracts business logic from iOS (Swift/SwiftUI) projects:
- SwiftUI Views and user flows
- ViewModels/ObservableObjects
- Swift data models (Codable)
- Mock data analysis
- API contracts (URLSession)
- Swift state machines (enums)
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.analyzers.business_logic_analyzer import (
    APIContract,
    BusinessLogicAnalysis,
    BusinessRule,
    BusinessRuleType,
    DataModel,
    StateMachine,
    UserFlow,
)


class IOSBusinessAnalyzer:
    """Analyzes iOS (Swift/SwiftUI) projects for business logic"""

    def __init__(self, project_path: Path, analysis: BusinessLogicAnalysis) -> None:
        """
        Initialize the iOS analyzer.

        Args:
            project_path: Root path of the iOS project
            analysis: Shared analysis result object
        """
        self.project_path = project_path
        self.analysis = analysis

    def analyze(self) -> None:
        """Perform complete iOS business logic analysis."""
        swift_files = list(self.project_path.rglob("*.swift"))

        for file_path in swift_files:
            self._analyze_swift_file(file_path)

        # Analyze SwiftUI Views for user flows
        self._analyze_swiftui_views()

        # Analyze ViewModels/ObservableObjects
        self._analyze_swift_viewmodels()

        # Analyze Swift models
        self._analyze_swift_models()

        # Analyze mock data
        self._analyze_swift_mock_data()

    def _analyze_swift_file(self, file_path: Path) -> None:
        """Analyze a Swift source file."""
        try:
            content = file_path.read_text(encoding="utf-8")

            # Extract business rules from comments
            self._extract_business_rules_from_comments(content, str(file_path))

            # Extract validations (Swift guard statements)
            self._extract_swift_validations(content, str(file_path))

            # Extract error handling
            self._extract_swift_error_handling(content, str(file_path))

        except Exception as e:
            print(f"Warning: Could not analyze Swift file {file_path}: {e}")

    def _analyze_swiftui_views(self) -> None:
        """Analyze SwiftUI Views for user flows."""
        view_files = [
            f
            for f in self.project_path.rglob("*.swift")
            if "View" in f.stem and "ViewModel" not in f.stem
        ]

        for view_file in view_files:
            try:
                content = view_file.read_text(encoding="utf-8")

                # Extract view name
                view_match = re.search(r"struct\s+(\w+):\s*View", content)
                if not view_match:
                    continue

                view_name = view_match.group(1)

                # Extract Button actions
                buttons = re.findall(
                    r'Button\(["\']([^"\']+)["\'].*?\{(.*?)\}',
                    content,
                    re.DOTALL,
                )

                # Extract NavigationLink destinations
                nav_links = re.findall(
                    r"NavigationLink\(.*?destination:\s*(\w+)", content
                )

                # Create user flow
                if buttons or nav_links:
                    steps = [f"Tap {btn[0]}" for btn in buttons]
                    steps.extend([f"Navigate to {dest}" for dest in nav_links])

                    flow = UserFlow(
                        name=view_name.replace("View", ""),
                        description=f"User flow for {view_name}",
                        steps=steps,
                        entry_point=view_name,
                        success_outcome="Complete interaction",
                        source_files=[str(view_file)],
                    )

                    self.analysis.user_flows.append(flow)

            except Exception as e:
                print(f"Warning: Could not analyze SwiftUI View {view_file}: {e}")

    def _analyze_swift_viewmodels(self) -> None:
        """Analyze Swift ViewModels/ObservableObjects."""
        vm_files = list(self.project_path.rglob("*ViewModel.swift"))

        for vm_file in vm_files:
            try:
                content = vm_file.read_text(encoding="utf-8")

                # Extract class name
                class_match = re.search(
                    r"class\s+(\w+ViewModel):\s*ObservableObject", content
                )
                if not class_match:
                    continue

                class_name = class_match.group(1)

                # Extract public methods
                methods = re.findall(
                    r"func\s+(\w+)\([^)]*\)\s*(?:->.*?)?\{", content
                )

                # Create user flow
                flow = UserFlow(
                    name=class_name.replace("ViewModel", ""),
                    description=f"User flow for {class_name}",
                    steps=[f"User {method}" for method in methods],
                    entry_point=f"{class_name}Screen",
                    success_outcome="State updated",
                    source_files=[str(vm_file)],
                )

                self.analysis.user_flows.append(flow)

            except Exception as e:
                print(f"Warning: Could not analyze Swift ViewModel {vm_file}: {e}")

    def _analyze_swift_models(self) -> None:
        """Analyze Swift data models."""
        model_files = [
            f
            for f in self.project_path.rglob("*.swift")
            if "Model" in f.stem or f.parent.name == "Models"
        ]

        for model_file in model_files:
            try:
                content = model_file.read_text(encoding="utf-8")

                # Extract struct/class definitions
                for match in re.finditer(
                        r"(?:struct|class)\s+(\w+):\s*(?:Codable|Identifiable|Hashable)"
                        r"(?:.*?)\{(.*?)\n\}",
                        content,
                        re.DOTALL,
                ):
                    model_name = match.group(1)
                    body = match.group(2)

                    # Parse properties
                    fields: Dict[str, str] = {}
                    for prop_match in re.finditer(
                            r"(?:var|let)\s+(\w+):\s+([^\n=]+)", body
                    ):
                        prop_name = prop_match.group(1)
                        prop_type = prop_match.group(2).strip()
                        fields[prop_name] = prop_type

                    if fields:
                        model = DataModel(
                            name=model_name,
                            fields=fields,
                            source_file=str(model_file),
                        )
                        self.analysis.data_models.append(model)

            except Exception as e:
                print(f"Warning: Could not analyze Swift model {model_file}: {e}")

    def _analyze_swift_mock_data(self) -> None:
        """Analyze Swift mock data."""
        mock_files = [
            f
            for f in self.project_path.rglob("*.swift")
            if "Mock" in f.stem or "Preview" in f.stem
        ]

        for mock_file in mock_files:
            try:
                content = mock_file.read_text(encoding="utf-8")

                # Extract static mock arrays
                for match in re.finditer(
                        r"static\s+(?:let|var)\s+(\w+):\s*\[(\w+)\]\s*=\s*\[(.*?)\]",
                        content,
                        re.DOTALL,
                ):
                    entity_name = match.group(1)
                    entity_type = match.group(2)
                    array_content = match.group(3)

                    # Count items
                    items = [
                        item.strip()
                        for item in array_content.split(f"{entity_type}(")
                        if item.strip()
                    ]
                    count = len(items)

                    if count > 0:
                        self.analysis.mock_data[entity_name] = {
                            "count": count,
                            "type": entity_type,
                            "source": str(mock_file),
                        }

            except Exception as e:
                print(f"Warning: Could not analyze Swift mock data {mock_file}: {e}")

    def _extract_business_rules_from_comments(
            self, content: str, file_path: str
    ) -> None:
        """Extract business rules from TODO and comments."""
        todos = re.findall(r"//\s*TODO:?\s*(.+)", content)
        for todo in todos:
            if any(
                    keyword in todo.lower()
                    for keyword in ["validate", "check", "auth", "permission", "rule"]
            ):
                rule = BusinessRule(
                    type=BusinessRuleType.VALIDATION,
                    description=todo.strip(),
                    condition="Not yet implemented",
                    source_file=file_path,
                )
                self.analysis.business_rules.append(rule)

    def _extract_swift_validations(self, content: str, file_path: str) -> None:
        """Extract Swift validation logic (guard statements)."""
        guards = re.findall(
            r"guard\s+(.*?)\s+else\s*\{([^}]*)\}", content, re.DOTALL
        )

        for condition, else_body in guards:
            # Extract error message if present
            error_msg_match = re.search(r'["\'](.+?)["\']', else_body)
            error_msg = (
                error_msg_match.group(1) if error_msg_match else "Validation failed"
            )

            rule = BusinessRule(
                type=BusinessRuleType.VALIDATION,
                description=f"Guard: {condition.strip()}",
                condition=condition.strip(),
                source_file=file_path,
                error_messages=[error_msg],
            )
            self.analysis.business_rules.append(rule)

    def _extract_swift_error_handling(self, content: str, file_path: str) -> None:
        """Extract Swift error handling (do-catch, throws)."""
        catches = re.findall(
            r"catch\s+(?:let\s+)?(\w+)?\s*\{([^}]+)\}", content
        )

        for error_var, _ in catches:
            error_type = error_var or "Error"
            rule = BusinessRule(
                type=BusinessRuleType.ERROR_HANDLING,
                description=f"Handle {error_type}",
                condition=f"When {error_type} is thrown",
                source_file=file_path,
            )
            self.analysis.business_rules.append(rule)

    def extract_state_machines(self) -> None:
        """Extract state machines from Swift enums."""
        swift_files = list(self.project_path.rglob("*.swift"))

        for swift_file in swift_files:
            try:
                content = swift_file.read_text(encoding="utf-8")

                # Find enums that represent states
                enum_matches = re.finditer(
                    r"enum\s+(\w+State)\s*\{(.*?)\n\}", content, re.DOTALL
                )

                for match in enum_matches:
                    state_name = match.group(1)
                    body = match.group(2)

                    # Extract cases
                    states = re.findall(r"case\s+(\w+)", body)

                    if len(states) > 1:
                        transitions = self._find_state_transitions(content, states)

                        state_machine = StateMachine(
                            name=state_name,
                            states=states,
                            transitions=transitions,
                            initial_state=states[0] if states else "Unknown",
                            source_file=str(swift_file),
                        )
                        self.analysis.state_machines.append(state_machine)

            except Exception as e:
                print(
                    f"Warning: Could not extract Swift state machine from {swift_file}: {e}"
                )

    def _find_state_transitions(
            self, content: str, states: List[str]
    ) -> Dict[str, List[str]]:
        """Find state transitions in switch expressions."""
        transitions: Dict[str, List[str]] = {state: [] for state in states}

        for from_state in states:
            pattern = rf"{from_state}.*?=\s*(\w+)"
            matches = re.findall(pattern, content)
            for to_state in matches:
                if to_state in states and to_state not in transitions[from_state]:
                    transitions[from_state].append(to_state)

        return transitions

    def generate_api_contracts(self) -> None:
        """Generate API contracts from URLSession calls."""
        for file_path in self.project_path.rglob("*.swift"):
            try:
                content = file_path.read_text(encoding="utf-8")

                # Look for URLSession calls
                url_pattern = r'URL\(string:\s*"([^"]+)"\)'
                url_matches = list(re.finditer(url_pattern, content))

                for url_match in url_matches:
                    url = url_match.group(1)

                    # Find HTTP method in context
                    url_pos = url_match.start()
                    context_start = max(0, url_pos - 500)
                    context_end = min(len(content), url_pos + 500)
                    context = content[context_start:context_end]

                    method_match = re.search(
                        r'httpMethod\s*=\s*"(GET|POST|PUT|DELETE|PATCH)"', context
                    )
                    method = method_match.group(1) if method_match else "GET"

                    # Find schemas
                    schemas = re.findall(
                        r"struct\s+(\w+):\s*Codable\s*{([^}]+)}",
                        context,
                        re.MULTILINE,
                    )

                    request_schema: Dict[str, Any] = {}
                    response_schema: Dict[str, Any] = {}

                    if schemas:
                        if len(schemas) > 0:
                            struct_name, fields = schemas[0]
                            response_schema = {
                                "type": struct_name,
                                "fields": self._parse_swift_fields(fields),
                            }
                        if len(schemas) > 1:
                            struct_name, fields = schemas[1]
                            request_schema = {
                                "type": struct_name,
                                "fields": self._parse_swift_fields(fields),
                            }

                    # Authentication
                    auth: Optional[str] = None
                    if "Authorization" in context or "Bearer" in context:
                        auth = "Bearer Token"

                    contract = APIContract(
                        endpoint=url,
                        method=method,
                        request_schema=request_schema,
                        response_schema=response_schema,
                        authentication=auth,
                        description=f"iOS API call from {file_path.name}",
                        source_file=str(file_path),
                    )

                    # Extract error handling
                    if "catch" in context or "Result" in context:
                        contract.error_responses = [
                            {"type": "NetworkError", "description": "Network failure"},
                            {
                                "type": "DecodingError",
                                "description": "JSON parsing error",
                            },
                        ]

                    self.analysis.api_contracts.append(contract)

            except Exception as e:
                print(f"Warning: Could not analyze API contracts in {file_path}: {e}")

    def _parse_swift_fields(self, fields_str: str) -> Dict[str, str]:
        """Parse Swift struct fields."""
        fields_dict: Dict[str, str] = {}
        field_matches = re.findall(r"let\s+(\w+):\s*(\w+)", fields_str)
        for name, type_name in field_matches:
            fields_dict[name] = type_name
        return fields_dict
