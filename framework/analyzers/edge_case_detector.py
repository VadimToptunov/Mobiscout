"""
Edge Case Detector

Detects edge cases and boundary conditions from source code:
- Boundary conditions (comparisons with constants)
- Null/nil safety checks
- Empty collection/string checks
- Overflow/underflow patterns
- Generates test data for edge cases
"""

import re
from pathlib import Path
from typing import List, Set

from framework.analyzers.business_logic_analyzer import (
    BusinessLogicAnalysis,
    BusinessRuleType,
    EdgeCase,
)


class EdgeCaseDetector:
    """Detects edge cases from code analysis"""

    def __init__(self, project_path: Path, analysis: BusinessLogicAnalysis) -> None:
        """
        Initialize the edge case detector.

        Args:
            project_path: Root path of the project
            analysis: Shared analysis result object
        """
        self.project_path = project_path
        self.analysis = analysis

    def detect(self) -> None:
        """Detect all edge cases from source code."""
        # Boundary conditions
        self._detect_boundary_conditions()

        # Null/nil checks
        self._detect_null_checks()

        # Empty collection checks
        self._detect_empty_checks()

        # Overflow/underflow patterns
        self._detect_overflow_patterns()

    def _detect_boundary_conditions(self) -> None:
        """Detect boundary condition checks."""
        all_files = (
                list(self.project_path.rglob("*.kt"))
                + list(self.project_path.rglob("*.java"))
                + list(self.project_path.rglob("*.swift"))
        )

        seen_boundaries: Set[tuple] = set()

        for file_path in all_files:
            try:
                content = file_path.read_text(encoding="utf-8")

                # Find comparisons with boundaries
                boundaries = re.findall(r"(\w+)\s*([<>=!]+)\s*(\d+)", content)

                for var_name, operator, value in boundaries:
                    if operator in ["<", "<=", ">", ">="] and value != "0":
                        boundary_key = (var_name, operator, value, str(file_path))

                        if boundary_key not in seen_boundaries:
                            seen_boundaries.add(boundary_key)

                            test_values = self._generate_boundary_test_values(
                                int(value), operator
                            )

                            edge_case = EdgeCase(
                                type="boundary",
                                description=(
                                    f"Boundary check: {var_name} {operator} {value}"
                                ),
                                test_data=test_values,
                                source_file=str(file_path),
                                severity="high",
                            )
                            self.analysis.edge_cases.append(edge_case)

            except Exception as e:
                print(f"Warning: Could not detect boundaries in {file_path}: {e}")

    def _generate_boundary_test_values(
            self, boundary: int, operator: str
    ) -> List[int]:
        """Generate test values for boundary conditions."""
        if operator in ["<", "<="]:
            return [boundary - 1, boundary, boundary + 1]
        elif operator in [">", ">="]:
            return [boundary - 1, boundary, boundary + 1]
        else:
            return [boundary]

    def _detect_null_checks(self) -> None:
        """Detect null/nil safety checks."""
        all_files = (
                list(self.project_path.rglob("*.kt"))
                + list(self.project_path.rglob("*.swift"))
        )

        seen_null_checks: Set[tuple] = set()

        for file_path in all_files:
            try:
                content = file_path.read_text(encoding="utf-8")

                # Kotlin null checks
                kt_null_checks = re.findall(r"(\w+)\s*[?!]=\s*null", content)

                # Swift nil checks
                swift_nil_checks = re.findall(
                    r"(?:if|guard)\s+let\s+(\w+)", content
                )

                all_checks = set(kt_null_checks + swift_nil_checks)

                for var_name in all_checks:
                    null_check_key = (var_name, str(file_path))

                    if null_check_key not in seen_null_checks:
                        seen_null_checks.add(null_check_key)

                        edge_case = EdgeCase(
                            type="null",
                            description=f"Null safety check for {var_name}",
                            test_data=[None, "valid_value"],
                            source_file=str(file_path),
                            severity="high",
                        )
                        self.analysis.edge_cases.append(edge_case)

            except Exception as e:
                print(f"Warning: Could not detect null checks in {file_path}: {e}")

    def _detect_empty_checks(self) -> None:
        """Detect empty collection/string checks."""
        all_files = (
                list(self.project_path.rglob("*.kt"))
                + list(self.project_path.rglob("*.swift"))
        )

        seen_empty_checks: Set[tuple] = set()

        for file_path in all_files:
            try:
                content = file_path.read_text(encoding="utf-8")

                # isEmpty checks
                empty_checks = re.findall(r"(\w+)\.isEmpty\(\)", content)

                for var_name in set(empty_checks):
                    empty_check_key = (var_name, str(file_path))

                    if empty_check_key not in seen_empty_checks:
                        seen_empty_checks.add(empty_check_key)

                        edge_case = EdgeCase(
                            type="empty",
                            description=f"Empty check for {var_name}",
                            test_data=[[], ["item"], "", "text"],
                            source_file=str(file_path),
                            severity="medium",
                        )
                        self.analysis.edge_cases.append(edge_case)

            except Exception as e:
                print(f"Warning: Could not detect empty checks in {file_path}: {e}")

    def _detect_overflow_patterns(self) -> None:
        """Detect potential overflow/underflow patterns."""
        all_files = (
                list(self.project_path.rglob("*.kt"))
                + list(self.project_path.rglob("*.java"))
        )

        seen_overflow: Set[tuple] = set()

        for file_path in all_files:
            try:
                content = file_path.read_text(encoding="utf-8")

                # Arithmetic operations
                arithmetic = re.findall(r"(\w+)\s*([+\-*/])\s*(\w+)", content)

                for left, op, right in arithmetic:
                    if op in ["+", "*"]:
                        overflow_key = (left, op, right)

                        if overflow_key not in seen_overflow:
                            seen_overflow.add(overflow_key)
                            edge_case = EdgeCase(
                                type="overflow",
                                description=f"Potential overflow: {left} {op} {right}",
                                test_data=["MAX_VALUE", "MIN_VALUE", 0, 1, -1],
                                source_file=str(file_path),
                                severity="medium",
                            )
                            self.analysis.edge_cases.append(edge_case)

            except Exception as e:
                print(
                    f"Warning: Could not detect overflow patterns in {file_path}: {e}"
                )

    def generate_negative_test_cases(self) -> None:
        """Generate negative test cases from business rules and edge cases."""
        # From validations
        for rule in self.analysis.business_rules:
            if rule.type == BusinessRuleType.VALIDATION:
                negative_case = {
                    "name": f"Negative: {rule.description}",
                    "type": "negative",
                    "description": f"Test violation of: {rule.condition}",
                    "expected_outcome": "Validation error",
                    "error_messages": rule.error_messages,
                    "priority": "high",
                    "source": [rule.source_file] if rule.source_file else [],
                }
                self.analysis.negative_test_cases.append(negative_case)

        # From edge cases
        for edge_case in self.analysis.edge_cases:
            if edge_case.severity in ["high", "critical"]:
                negative_case = {
                    "name": f"Negative: {edge_case.description}",
                    "type": "negative",
                    "description": f"Test {edge_case.type} edge case",
                    "test_data": edge_case.test_data,
                    "expected_outcome": "Handle edge case gracefully",
                    "priority": edge_case.severity,
                    "source": [edge_case.source_file] if edge_case.source_file else [],
                }
                self.analysis.negative_test_cases.append(negative_case)

        # From user flows - generate failure scenarios
        for flow in self.analysis.user_flows:
            negative_case = {
                "name": f"Negative: {flow.name} - Invalid Input",
                "type": "negative",
                "description": f"Test {flow.name} with invalid input",
                "steps": flow.steps,
                "expected_outcome": "Show error message",
                "priority": "high",
                "source": [flow.source_files[0]] if flow.source_files else [],
            }
            self.analysis.negative_test_cases.append(negative_case)
