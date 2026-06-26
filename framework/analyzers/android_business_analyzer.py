"""
Android Business Logic Analyzer

Extracts business logic from Android (Kotlin/Java) projects:
- ViewModels and user flows
- Repositories and data access patterns
- Data models
- Mock data analysis
- API contracts (Retrofit)
- Kotlin state machines
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


class AndroidBusinessAnalyzer:
    """Analyzes Android (Kotlin/Java) projects for business logic"""

    def __init__(self, project_path: Path, analysis: BusinessLogicAnalysis) -> None:
        """
        Initialize the Android analyzer.

        Args:
            project_path: Root path of the Android project
            analysis: Shared analysis result object
        """
        self.project_path = project_path
        self.analysis = analysis

    def analyze(self) -> None:
        """Perform complete Android business logic analysis."""
        # Analyze Kotlin/Java files
        kotlin_files = list(self.project_path.rglob("*.kt"))
        java_files = list(self.project_path.rglob("*.java"))

        for file_path in kotlin_files + java_files:
            self._analyze_file(file_path)

        # Analyze ViewModels for flows
        self._analyze_viewmodels()

        # Analyze Repositories for data access patterns
        self._analyze_repositories()

        # Analyze data models
        self._analyze_models()

        # Analyze mock data for business scenarios
        self._analyze_mock_data()

    def _analyze_file(self, file_path: Path) -> None:
        """Analyze a single source file."""
        try:
            content = file_path.read_text(encoding="utf-8")

            # Extract business rules from comments
            self._extract_business_rules_from_comments(content, str(file_path))

            # Extract validation rules
            self._extract_validations(content, str(file_path))

            # Extract error handling
            self._extract_error_handling(content, str(file_path))

        except Exception as e:
            print(f"Warning: Could not analyze {file_path}: {e}")

    def _analyze_viewmodels(self) -> None:
        """Analyze ViewModels to extract user flows."""
        viewmodel_files = list(self.project_path.rglob("*ViewModel.kt"))

        for vm_file in viewmodel_files:
            try:
                content = vm_file.read_text(encoding="utf-8")

                # Extract flow name from class name
                class_match = re.search(r"class\s+(\w+)ViewModel", content)
                if not class_match:
                    continue

                flow_name = class_match.group(1)

                # Extract public methods (user actions)
                methods = re.findall(r"fun\s+(\w+)\([^)]*\)\s*\{", content)

                # Create user flow
                flow = UserFlow(
                    name=flow_name,
                    description=f"User flow for {flow_name}",
                    steps=[f"User {method}" for method in methods],
                    entry_point=f"{flow_name}Screen",
                    success_outcome="Navigate to next screen",
                    source_files=[str(vm_file)],
                )

                self.analysis.user_flows.append(flow)

            except Exception as e:
                print(f"Warning: Could not analyze ViewModel {vm_file}: {e}")

    def _analyze_repositories(self) -> None:
        """Analyze repositories for data access patterns."""
        repo_files = list(self.project_path.rglob("*Repository.kt"))

        for repo_file in repo_files:
            try:
                content = repo_file.read_text(encoding="utf-8")

                # Extract interface methods
                interface_methods = re.findall(
                    r"suspend\s+fun\s+(\w+)\([^)]*\):\s*(\w+)", content
                )

                for method_name, return_type in interface_methods:
                    # Create business rule for data access
                    rule = BusinessRule(
                        type=BusinessRuleType.AUTHORIZATION,
                        description=f"Data access: {method_name} returns {return_type}",
                        condition="User must be authenticated",
                        source_file=str(repo_file),
                        related_entities=[return_type],
                    )
                    self.analysis.business_rules.append(rule)

            except Exception as e:
                print(f"Warning: Could not analyze Repository {repo_file}: {e}")

    def _analyze_models(self) -> None:
        """Analyze data models."""
        model_files = list(self.project_path.rglob("models/*.kt"))

        for model_file in model_files:
            try:
                content = model_file.read_text(encoding="utf-8")

                # Extract data class
                class_match = re.search(
                    r"data\s+class\s+(\w+)\s*\((.*?)\)", content, re.DOTALL
                )

                if not class_match:
                    continue

                class_name = class_match.group(1)
                params = class_match.group(2)

                # Parse fields
                fields: Dict[str, str] = {}
                for field_match in re.finditer(r"val\s+(\w+):\s+([^,\n]+)", params):
                    field_name = field_match.group(1)
                    field_type = field_match.group(2).strip()
                    fields[field_name] = field_type

                model = DataModel(
                    name=class_name, fields=fields, source_file=str(model_file)
                )

                self.analysis.data_models.append(model)

            except Exception as e:
                print(f"Warning: Could not analyze model {model_file}: {e}")

    def _analyze_mock_data(self) -> None:
        """Analyze mock data to understand business scenarios."""
        mock_files = list(self.project_path.rglob("mock/*.kt"))

        for mock_file in mock_files:
            try:
                content = mock_file.read_text(encoding="utf-8")

                # Extract lazy property with mock data
                lazy_match = re.search(
                    r"val\s+MockData\.(\w+).*?by\s+lazy\s*\{(.*?)\}",
                    content,
                    re.DOTALL,
                )

                if lazy_match:
                    entity_name = lazy_match.group(1)
                    lazy_body = lazy_match.group(2)

                    # Extract range for test data count
                    range_match = re.search(r"\((\d+)L?\.\.(\d+)L?\)", lazy_body)
                    if range_match:
                        start, end = range_match.groups()
                        self.analysis.mock_data[entity_name] = {
                            "count": int(end) - int(start) + 1,
                            "start_id": int(start),
                            "end_id": int(end),
                            "source": str(mock_file),
                        }

            except Exception as e:
                print(f"Warning: Could not analyze mock data {mock_file}: {e}")

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

    def _extract_validations(self, content: str, file_path: str) -> None:
        """Extract validation logic."""
        requires = re.findall(
            r'require\((.*?)\)\s*\{?\s*["\'](.+?)["\']', content
        )
        for condition, message in requires:
            rule = BusinessRule(
                type=BusinessRuleType.VALIDATION,
                description=f"Validation: {condition}",
                condition=condition.strip(),
                source_file=file_path,
                error_messages=[message],
            )
            self.analysis.business_rules.append(rule)

    def _extract_error_handling(self, content: str, file_path: str) -> None:
        """Extract error handling logic."""
        catches = re.findall(
            r"catch\s*\(\s*\w+:\s*(\w+)\s*\)\s*\{([^}]+)\}", content
        )
        for exception_type, _ in catches:
            rule = BusinessRule(
                type=BusinessRuleType.ERROR_HANDLING,
                description=f"Handle {exception_type}",
                condition=f"When {exception_type} occurs",
                source_file=file_path,
            )
            self.analysis.business_rules.append(rule)

    def extract_state_machines(self) -> None:
        """Extract state machines from Kotlin sealed classes."""
        kt_files = list(self.project_path.rglob("*.kt"))

        for kt_file in kt_files:
            try:
                content = kt_file.read_text(encoding="utf-8")

                # Find sealed classes that represent states
                sealed_matches = re.finditer(
                    r"sealed\s+class\s+(\w+State)\s*\{(.*?)\n\}",
                    content,
                    re.DOTALL,
                )

                for match in sealed_matches:
                    state_name = match.group(1)
                    body = match.group(2)

                    # Extract state variants
                    states = re.findall(
                        r"(?:data\s+)?class\s+(\w+)\s*(?:\(.*?\))?", body
                    )
                    states = [s for s in states if s != state_name]

                    if len(states) > 1:
                        transitions = self._find_state_transitions(content, states)

                        state_machine = StateMachine(
                            name=state_name,
                            states=states,
                            transitions=transitions,
                            initial_state=states[0] if states else "Unknown",
                            source_file=str(kt_file),
                        )
                        self.analysis.state_machines.append(state_machine)

            except Exception as e:
                print(f"Warning: Could not extract state machine from {kt_file}: {e}")

    def _find_state_transitions(
            self, content: str, states: List[str]
    ) -> Dict[str, List[str]]:
        """Find state transitions in when/switch expressions."""
        transitions: Dict[str, List[str]] = {state: [] for state in states}

        for from_state in states:
            pattern = rf"{from_state}.*?=\s*(\w+)"
            matches = re.findall(pattern, content)
            for to_state in matches:
                if to_state in states and to_state not in transitions[from_state]:
                    transitions[from_state].append(to_state)

        return transitions

    def generate_api_contracts(self) -> None:
        """Generate API contracts from Retrofit service interfaces."""
        for file_path in self.project_path.rglob("*.kt"):
            try:
                content = file_path.read_text(encoding="utf-8")

                # Look for @GET, @POST, @PUT, @DELETE annotations
                api_methods = re.findall(
                    r"@(GET|POST|PUT|DELETE|PATCH)\(\"([^\"]+)\"\)\s+"
                    r"(?:suspend\s+)?fun\s+(\w+)\s*\([^)]*\)\s*:\s*([^\s{]+)",
                    content,
                    re.MULTILINE,
                )

                for method, endpoint, func_name, return_type in api_methods:
                    # Extract request parameters
                    func_match = re.search(
                        rf"fun\s+{func_name}\s*\(([^)]*)\)", content
                    )
                    request_params: Dict[str, Any] = {}
                    if func_match:
                        params_str = func_match.group(1)
                        body_params = re.findall(
                            r"@Body\s+(\w+):\s*(\w+)", params_str
                        )
                        query_params = re.findall(
                            r"@Query\(\"(\w+)\"\)\s+(\w+):\s*(\w+)", params_str
                        )
                        path_params = re.findall(
                            r"@Path\(\"(\w+)\"\)\s+(\w+):\s*(\w+)", params_str
                        )

                        if body_params:
                            request_params["body"] = {
                                name: type_name for name, type_name in body_params
                            }
                        if query_params:
                            request_params["query"] = {
                                param: type_name
                                for param, _, type_name in query_params
                            }
                        if path_params:
                            request_params["path"] = {
                                param: type_name
                                for param, _, type_name in path_params
                            }

                    # Extract authentication info
                    auth: Optional[str] = None
                    if "@Headers" in content or "Authorization" in content:
                        auth = "Bearer Token"

                    # Create API contract
                    contract = APIContract(
                        endpoint=endpoint,
                        method=method,
                        request_schema=request_params,
                        response_schema={"type": return_type},
                        authentication=auth,
                        description=f"API endpoint: {func_name}",
                        source_file=str(file_path),
                    )

                    # Extract error responses
                    func_start = content.find(f"fun {func_name}")
                    if func_start != -1:
                        context_start = max(0, func_start - 500)
                        context_end = min(len(content), func_start + 1000)
                        func_context = content[context_start:context_end]

                        error_codes = re.findall(r"(4\d{2}|5\d{2})", func_context)
                        if error_codes:
                            contract.error_responses = [
                                {"code": code, "description": "Error response"}
                                for code in set(error_codes)
                            ]

                    self.analysis.api_contracts.append(contract)

            except Exception as e:
                print(f"Warning: Could not analyze API contracts in {file_path}: {e}")
