"""EdgeCaseDetector scans Kotlin/Java/Swift sources for boundary comparisons,
null/nil checks, empty-collection checks and overflow-prone arithmetic, emitting
EdgeCase records with generated test data. It also derives negative test cases
from validations, high-severity edge cases and user flows. Pure text analysis
over a project dir; previously 0% covered. Expected values are derived from the
module's regexes and test-value generators.
"""

from framework.analyzers.business_logic_analyzer import (
    BusinessLogicAnalysis,
    BusinessRule,
    BusinessRuleType,
    EdgeCase,
    UserFlow,
)
from framework.analyzers.edge_case_detector import EdgeCaseDetector


def _detector(tmp_path, files: dict) -> EdgeCaseDetector:
    for name, content in files.items():
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
    return EdgeCaseDetector(tmp_path, BusinessLogicAnalysis())


def _cases_of(det, type_):
    return [e for e in det.analysis.edge_cases if e.type == type_]


# --------------------------------------------------------------------------- #
# Boundary conditions
# --------------------------------------------------------------------------- #
def test_boundary_condition_detected_with_test_values(tmp_path):
    det = _detector(tmp_path, {"Age.kt": "fun ok(age: Int) = age >= 18\n"})
    det.detect()
    boundary = next(e for e in _cases_of(det, "boundary") if "age >= 18" in e.description)
    assert boundary.severity == "high"
    assert boundary.description == "Boundary check: age >= 18"
    # >= boundary -> [17, 18, 19]
    assert boundary.test_data == [17, 18, 19]


def test_comparison_with_zero_is_ignored(tmp_path):
    det = _detector(tmp_path, {"Z.kt": "fun p(x: Int) = x > 0\n"})
    det.detect()
    assert _cases_of(det, "boundary") == []


def test_equality_operator_is_not_a_boundary(tmp_path):
    # Only <, <=, >, >= qualify; == / != do not.
    det = _detector(tmp_path, {"Eq.kt": "fun p(x: Int) = x == 42\n"})
    det.detect()
    assert _cases_of(det, "boundary") == []


def test_duplicate_boundary_in_same_file_deduped(tmp_path):
    det = _detector(tmp_path, {"Dup.kt": "fun a(x: Int) = x > 5\nfun b(x: Int) = x > 5\n"})
    det.detect()
    assert len([e for e in _cases_of(det, "boundary") if "x > 5" in e.description]) == 1


def test_generate_boundary_test_values_directly():
    det = EdgeCaseDetector(".", BusinessLogicAnalysis())  # path unused for this pure helper
    assert det._generate_boundary_test_values(10, "<") == [9, 10, 11]
    assert det._generate_boundary_test_values(10, "<=") == [9, 10, 11]
    assert det._generate_boundary_test_values(10, ">") == [9, 10, 11]
    assert det._generate_boundary_test_values(10, ">=") == [9, 10, 11]
    assert det._generate_boundary_test_values(10, "==") == [10]


# --------------------------------------------------------------------------- #
# Null / nil checks
# --------------------------------------------------------------------------- #
def test_kotlin_null_check_detected(tmp_path):
    det = _detector(tmp_path, {"N.kt": "fun f(user: User?) { if (user != null) use(user) }\n"})
    det.detect()
    null_case = next(e for e in _cases_of(det, "null") if "user" in e.description)
    assert null_case.severity == "high"
    assert null_case.description == "Null safety check for user"
    assert null_case.test_data == [None, "valid_value"]


def test_swift_guard_let_detected_as_null(tmp_path):
    det = _detector(tmp_path, {"N.swift": "func f() { guard let account = maybe else { return } }\n"})
    det.detect()
    assert any("account" in e.description for e in _cases_of(det, "null"))


# --------------------------------------------------------------------------- #
# Empty collection / string checks
# --------------------------------------------------------------------------- #
def test_empty_check_detected(tmp_path):
    det = _detector(tmp_path, {"E.kt": "fun f(items: List<Int>) { if (items.isEmpty()) return }\n"})
    det.detect()
    empty = next(e for e in _cases_of(det, "empty") if "items" in e.description)
    assert empty.severity == "medium"
    assert empty.test_data == [[], ["item"], "", "text"]


# --------------------------------------------------------------------------- #
# Overflow / underflow arithmetic
# --------------------------------------------------------------------------- #
def test_overflow_detected_for_plus_and_star(tmp_path):
    det = _detector(tmp_path, {"O.kt": "fun total() { val t = price * qty }\n"})
    det.detect()
    overflow = next(e for e in _cases_of(det, "overflow") if e.description == "Potential overflow: price * qty")
    assert overflow.severity == "medium"
    assert overflow.test_data == ["MAX_VALUE", "MIN_VALUE", 0, 1, -1]


def test_subtraction_and_division_do_not_trigger_overflow(tmp_path):
    det = _detector(tmp_path, {"O.kt": "fun f() { val a = x - y; val b = m / n }\n"})
    det.detect()
    assert _cases_of(det, "overflow") == []


# --------------------------------------------------------------------------- #
# Language filtering: only relevant extensions are scanned
# --------------------------------------------------------------------------- #
def test_python_files_are_not_scanned(tmp_path):
    det = _detector(tmp_path, {"code.py": "x = age >= 18\n"})
    det.detect()
    assert det.analysis.edge_cases == []


def test_detect_on_empty_project(tmp_path):
    det = EdgeCaseDetector(tmp_path, BusinessLogicAnalysis())
    det.detect()
    assert det.analysis.edge_cases == []


# --------------------------------------------------------------------------- #
# Negative test case generation
# --------------------------------------------------------------------------- #
def test_negative_cases_from_validation_rule():
    analysis = BusinessLogicAnalysis()
    analysis.business_rules.append(
        BusinessRule(
            type=BusinessRuleType.VALIDATION,
            description="age must be >= 18",
            condition="age >= 18",
            source_file="Age.kt",
            error_messages=["Too young"],
        )
    )
    det = EdgeCaseDetector(".", analysis)
    det.generate_negative_test_cases()
    case = next(c for c in analysis.negative_test_cases if "age must be" in c["name"])
    assert case["type"] == "negative"
    assert case["expected_outcome"] == "Validation error"
    assert case["error_messages"] == ["Too young"]
    assert case["priority"] == "high"
    assert case["source"] == ["Age.kt"]


def test_negative_cases_only_from_high_severity_edge_cases():
    analysis = BusinessLogicAnalysis()
    analysis.edge_cases.append(EdgeCase(type="null", description="null user", severity="high", source_file="U.kt"))
    analysis.edge_cases.append(EdgeCase(type="empty", description="empty list", severity="medium"))
    det = EdgeCaseDetector(".", analysis)
    det.generate_negative_test_cases()
    names = [c["name"] for c in analysis.negative_test_cases]
    assert any("null user" in n for n in names)
    assert not any("empty list" in n for n in names)  # medium severity is skipped


def test_negative_cases_from_user_flow():
    analysis = BusinessLogicAnalysis()
    analysis.user_flows.append(
        UserFlow(
            name="Login",
            description="d",
            steps=["User signIn"],
            entry_point="LoginScreen",
            success_outcome="ok",
            source_files=["LoginViewModel.kt"],
        )
    )
    det = EdgeCaseDetector(".", analysis)
    det.generate_negative_test_cases()
    case = next(c for c in analysis.negative_test_cases if "Login" in c["name"])
    assert case["name"] == "Negative: Login - Invalid Input"
    assert case["expected_outcome"] == "Show error message"
    assert case["steps"] == ["User signIn"]
    assert case["source"] == ["LoginViewModel.kt"]
