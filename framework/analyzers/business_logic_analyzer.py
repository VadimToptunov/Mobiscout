"""
Business Logic Analyzer

Extracts business logic, rules, and user flows from source code:
- User authentication flows
- Business rules and validations
- Data models and relationships
- State machines and workflows
- Error handling logic
- iOS Swift/SwiftUI support
- Deep AST analysis
- Negative test case generation
- Edge case detection

This module serves as a coordinator, delegating platform-specific
analysis to AndroidBusinessAnalyzer and IOSBusinessAnalyzer.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class BusinessRuleType(Enum):
    """Types of business rules"""

    VALIDATION = "validation"
    AUTHORIZATION = "authorization"
    STATE_TRANSITION = "state_transition"
    CALCULATION = "calculation"
    ERROR_HANDLING = "error_handling"


@dataclass
class BusinessRule:
    """Represents a business rule extracted from code"""

    type: BusinessRuleType
    description: str
    condition: str
    source_file: str
    line_number: Optional[int] = None
    related_entities: List[str] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)


@dataclass
class UserFlow:
    """Represents a user flow/journey"""

    name: str
    description: str
    steps: List[str]
    entry_point: str
    success_outcome: str
    failure_outcomes: List[str] = field(default_factory=list)
    business_rules: List[BusinessRule] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)


@dataclass
class DataModel:
    """Represents a data model/entity"""

    name: str
    fields: Dict[str, str]  # field_name -> field_type
    validations: List[str] = field(default_factory=list)
    relationships: List[str] = field(default_factory=list)
    source_file: Optional[str] = None


@dataclass
class EdgeCase:
    """Represents an edge case detected in code"""

    type: str  # boundary, null, empty, overflow, etc.
    description: str
    test_data: List[Any] = field(default_factory=list)
    source_file: Optional[str] = None
    severity: str = "medium"  # low, medium, high, critical


@dataclass
class StateMachine:
    """Represents a state machine extracted from code"""

    name: str
    states: List[str]
    transitions: Dict[str, List[str]]  # from_state -> [to_states]
    initial_state: str
    final_states: List[str] = field(default_factory=list)
    source_file: Optional[str] = None


@dataclass
class APIContract:
    """Represents an API contract/specification"""

    endpoint: str
    method: str  # GET, POST, PUT, DELETE, etc.
    request_schema: Dict[str, Any] = field(default_factory=dict)
    response_schema: Dict[str, Any] = field(default_factory=dict)
    error_responses: List[Dict[str, Any]] = field(default_factory=list)
    authentication: Optional[str] = None
    rate_limit: Optional[str] = None
    description: Optional[str] = None
    source_file: Optional[str] = None


@dataclass
class BusinessLogicAnalysis:
    """Complete business logic analysis result"""

    user_flows: List[UserFlow] = field(default_factory=list)
    business_rules: List[BusinessRule] = field(default_factory=list)
    data_models: List[DataModel] = field(default_factory=list)
    state_machines: List[StateMachine] = field(default_factory=list)
    edge_cases: List[EdgeCase] = field(default_factory=list)
    api_contracts: List[APIContract] = field(default_factory=list)
    mock_data: Dict[str, Any] = field(default_factory=dict)
    negative_test_cases: List[Dict[str, Any]] = field(default_factory=list)
    platform: str = "android"  # android or ios


class BusinessLogicAnalyzer:
    """
    Analyzes source code to extract business logic.

    This class serves as a coordinator, delegating platform-specific
    analysis to specialized analyzers:
    - AndroidBusinessAnalyzer: Kotlin/Java analysis
    - IOSBusinessAnalyzer: Swift/SwiftUI analysis
    - EdgeCaseDetector: Edge case detection across all platforms
    """

    def __init__(self, project_path: Path) -> None:
        """
        Initialize the business logic analyzer.

        Args:
            project_path: Root path of the project to analyze
        """
        self.project_path = Path(project_path)
        self.analysis = BusinessLogicAnalysis()
        self.platform = self._detect_platform()

        # Lazy import to avoid circular dependencies
        self._android_analyzer: Optional[Any] = None
        self._ios_analyzer: Optional[Any] = None
        self._edge_case_detector: Optional[Any] = None

    def _detect_platform(self) -> str:
        """Detect if project is Android or iOS."""
        if list(self.project_path.rglob("*.swift")):
            return "ios"
        elif list(self.project_path.rglob("*.kt")) or list(
                self.project_path.rglob("*.java")
        ):
            return "android"
        else:
            return "unknown"

    @property
    def android_analyzer(self) -> Any:
        """Get or create Android analyzer (lazy initialization)."""
        if self._android_analyzer is None:
            from framework.analyzers.android_business_analyzer import (
                AndroidBusinessAnalyzer,
            )

            self._android_analyzer = AndroidBusinessAnalyzer(
                self.project_path, self.analysis
            )
        return self._android_analyzer

    @property
    def ios_analyzer(self) -> Any:
        """Get or create iOS analyzer (lazy initialization)."""
        if self._ios_analyzer is None:
            from framework.analyzers.ios_business_analyzer import IOSBusinessAnalyzer

            self._ios_analyzer = IOSBusinessAnalyzer(self.project_path, self.analysis)
        return self._ios_analyzer

    @property
    def edge_case_detector(self) -> Any:
        """Get or create edge case detector (lazy initialization)."""
        if self._edge_case_detector is None:
            from framework.analyzers.edge_case_detector import EdgeCaseDetector

            self._edge_case_detector = EdgeCaseDetector(
                self.project_path, self.analysis
            )
        return self._edge_case_detector

    def analyze(self) -> BusinessLogicAnalysis:
        """
        Perform complete business logic analysis.

        Returns:
            BusinessLogicAnalysis with extracted information
        """
        if self.platform == "android":
            self._analyze_android()
        elif self.platform == "ios":
            self._analyze_ios()
        else:
            # Try both
            self._analyze_android()
            self._analyze_ios()

        # Extract state machines
        self._extract_state_machines()

        # Detect edge cases
        self.edge_case_detector.detect()

        # Generate negative test cases
        self.edge_case_detector.generate_negative_test_cases()

        # Generate API contracts
        self._generate_api_contracts()

        # Set platform in analysis
        self.analysis.platform = self.platform

        return self.analysis

    def _analyze_android(self) -> None:
        """Analyze Android (Kotlin/Java) project."""
        self.android_analyzer.analyze()

    def _analyze_ios(self) -> None:
        """Analyze iOS (Swift/SwiftUI) project."""
        self.ios_analyzer.analyze()

    def _extract_state_machines(self) -> None:
        """Extract state machines from source code."""
        if self.platform == "android" or self.platform == "unknown":
            self.android_analyzer.extract_state_machines()

        if self.platform == "ios" or self.platform == "unknown":
            self.ios_analyzer.extract_state_machines()

    def _generate_api_contracts(self) -> None:
        """Generate API contracts from network calls and service definitions."""
        if self.platform == "android":
            self.android_analyzer.generate_api_contracts()
        elif self.platform == "ios":
            self.ios_analyzer.generate_api_contracts()

    def generate_test_scenarios(self) -> List[Dict[str, Any]]:
        """
        Generate test scenarios from business logic.

        Returns:
            List of test scenario dictionaries
        """
        scenarios: List[Dict[str, Any]] = []

        for flow in self.analysis.user_flows:
            # Happy path scenario
            scenarios.append(
                {
                    "name": f"{flow.name} - Happy Path",
                    "type": "positive",
                    "description": flow.description,
                    "steps": flow.steps,
                    "expected_outcome": flow.success_outcome,
                    "priority": "high",
                }
            )

            # Failure scenarios
            for failure in flow.failure_outcomes:
                scenarios.append(
                    {
                        "name": f"{flow.name} - {failure}",
                        "type": "negative",
                        "description": f"Test {failure} scenario",
                        "steps": flow.steps[:-1],  # All steps except last
                        "expected_outcome": failure,
                        "priority": "medium",
                    }
                )

        return scenarios

    def generate_bdd_features(self) -> str:
        """
        Generate BDD feature file from business logic.

        Returns:
            Gherkin feature file content
        """
        feature_content: List[str] = []

        for flow in self.analysis.user_flows:
            feature_content.append(f"Feature: {flow.name}")
            feature_content.append(f"  {flow.description}")
            feature_content.append("")

            # Generate scenario from flow
            feature_content.append(f"  Scenario: {flow.name} - Success")
            feature_content.append(f"    Given I am on the {flow.entry_point}")

            for step in flow.steps:
                feature_content.append(f"    When {step}")

            feature_content.append(f"    Then {flow.success_outcome}")
            feature_content.append("")

        return "\n".join(feature_content)

    def get_mock_test_data(self) -> Dict[str, Any]:
        """
        Get mock test data for testing.

        Returns:
            Dictionary with test data
        """
        return self.analysis.mock_data

    def export_to_json(self) -> Dict[str, Any]:
        """Export analysis to JSON-serializable dict."""
        return {
            "platform": self.platform,
            "user_flows": [
                {
                    "name": flow.name,
                    "description": flow.description,
                    "steps": flow.steps,
                    "entry_point": flow.entry_point,
                    "success_outcome": flow.success_outcome,
                    "failure_outcomes": flow.failure_outcomes,
                    "source_files": flow.source_files,
                }
                for flow in self.analysis.user_flows
            ],
            "business_rules": [
                {
                    "type": rule.type.value,
                    "description": rule.description,
                    "condition": rule.condition,
                    "source_file": rule.source_file,
                    "related_entities": rule.related_entities,
                    "error_messages": rule.error_messages,
                }
                for rule in self.analysis.business_rules
            ],
            "data_models": [
                {
                    "name": model.name,
                    "fields": model.fields,
                    "validations": model.validations,
                    "source_file": model.source_file,
                }
                for model in self.analysis.data_models
            ],
            "state_machines": [
                {
                    "name": sm.name,
                    "states": sm.states,
                    "transitions": sm.transitions,
                    "initial_state": sm.initial_state,
                    "final_states": sm.final_states,
                    "source_file": sm.source_file,
                }
                for sm in self.analysis.state_machines
            ],
            "edge_cases": [
                {
                    "type": ec.type,
                    "description": ec.description,
                    "test_data": ec.test_data,
                    "source_file": ec.source_file,
                    "severity": ec.severity,
                }
                for ec in self.analysis.edge_cases
            ],
            "api_contracts": [
                {
                    "endpoint": contract.endpoint,
                    "method": contract.method,
                    "request_schema": contract.request_schema,
                    "response_schema": contract.response_schema,
                    "error_responses": contract.error_responses,
                    "authentication": contract.authentication,
                    "rate_limit": contract.rate_limit,
                    "description": contract.description,
                    "source_file": contract.source_file,
                }
                for contract in self.analysis.api_contracts
            ],
            "negative_test_cases": self.analysis.negative_test_cases,
            "mock_data": self.analysis.mock_data,
        }
