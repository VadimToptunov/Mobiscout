"""AndroidBusinessAnalyzer mines business logic from Kotlin/Java sources — user
flows from ViewModels, data-access rules from Repositories, Codable-style data
models, mock-data ranges, validation/error-handling/TODO business rules, sealed-
class state machines and Retrofit API contracts. Pure text analysis over a
project dir; previously 0% covered. Every expected value here is derived from the
regexes in the module, not hand-waved.
"""

from framework.analyzers.android_business_analyzer import AndroidBusinessAnalyzer
from framework.analyzers.business_logic_analyzer import (
    BusinessLogicAnalysis,
    BusinessRule,
    BusinessRuleType,
    EdgeCase,
    UserFlow,
)


def _project(tmp_path, files: dict) -> AndroidBusinessAnalyzer:
    for name, content in files.items():
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
    return AndroidBusinessAnalyzer(tmp_path, BusinessLogicAnalysis())


# --------------------------------------------------------------------------- #
# ViewModels -> user flows
# --------------------------------------------------------------------------- #
def test_viewmodel_methods_become_a_user_flow(tmp_path):
    az = _project(
        tmp_path,
        {"LoginViewModel.kt": ("class LoginViewModel {\n" "  fun signIn() {}\n" "  fun signOut() {}\n" "}\n")},
    )
    az.analyze()
    flow = next(f for f in az.analysis.user_flows if f.name == "Login")
    assert flow.entry_point == "LoginScreen"
    assert flow.steps == ["User signIn", "User signOut"]
    assert flow.success_outcome == "Navigate to next screen"
    assert str(tmp_path / "LoginViewModel.kt") in flow.source_files


def test_viewmodel_without_matching_class_is_skipped(tmp_path):
    # File named *ViewModel.kt but no `class XViewModel` declaration -> no flow.
    az = _project(tmp_path, {"BrokenViewModel.kt": "// just a comment, no class here\n"})
    az.analyze()
    assert az.analysis.user_flows == []


# --------------------------------------------------------------------------- #
# Repositories -> authorization business rules
# --------------------------------------------------------------------------- #
def test_repository_suspend_methods_become_data_access_rules(tmp_path):
    az = _project(
        tmp_path,
        {"UserRepository.kt": ("interface UserRepository {\n" "  suspend fun getUser(id: Int): User\n" "}\n")},
    )
    az.analyze()
    rule = next(r for r in az.analysis.business_rules if r.description.startswith("Data access"))
    assert rule.type == BusinessRuleType.AUTHORIZATION
    assert rule.description == "Data access: getUser returns User"
    assert rule.condition == "User must be authenticated"
    assert rule.related_entities == ["User"]


# --------------------------------------------------------------------------- #
# models/ -> data models
# --------------------------------------------------------------------------- #
def test_data_class_fields_extracted(tmp_path):
    az = _project(
        tmp_path,
        {"models/Account.kt": ("data class Account(val id: Int, val name: String, val balance: Double)\n")},
    )
    az.analyze()
    model = next(m for m in az.analysis.data_models if m.name == "Account")
    assert model.fields == {"id": "Int", "name": "String", "balance": "Double"}
    assert model.source_file == str(tmp_path / "models/Account.kt")


def test_non_data_class_model_file_yields_no_model(tmp_path):
    az = _project(tmp_path, {"models/Helper.kt": "class Helper { fun noop() {} }\n"})
    az.analyze()
    assert az.analysis.data_models == []


# --------------------------------------------------------------------------- #
# mock/ -> mock data ranges
# --------------------------------------------------------------------------- #
def test_mock_data_range_count(tmp_path):
    az = _project(tmp_path, {"mock/MockData.kt": "val MockData.users by lazy { (1L..10L) }\n"})
    az.analyze()
    assert az.analysis.mock_data["users"] == {
        "count": 10,
        "start_id": 1,
        "end_id": 10,
        "source": str(tmp_path / "mock/MockData.kt"),
    }


# --------------------------------------------------------------------------- #
# Business rules from comments / require() / catch()
# --------------------------------------------------------------------------- #
def test_todo_comment_with_keyword_becomes_validation_rule(tmp_path):
    az = _project(tmp_path, {"Rules.kt": "// TODO: validate the email before submit\nfun submit() {}\n"})
    az.analyze()
    rule = next(r for r in az.analysis.business_rules if "email" in r.description)
    assert rule.type == BusinessRuleType.VALIDATION
    assert rule.description == "validate the email before submit"
    assert rule.condition == "Not yet implemented"


def test_todo_without_keyword_is_ignored(tmp_path):
    az = _project(tmp_path, {"Notes.kt": "// TODO: refactor this later\nfun x() {}\n"})
    az.analyze()
    assert all("refactor" not in r.description for r in az.analysis.business_rules)


def test_require_becomes_validation_rule_with_error_message(tmp_path):
    az = _project(tmp_path, {"Validate.kt": 'fun check(age: Int) { require(age > 18) { "Must be adult" } }\n'})
    az.analyze()
    rule = next(r for r in az.analysis.business_rules if r.description == "Validation: age > 18")
    assert rule.type == BusinessRuleType.VALIDATION
    assert rule.condition == "age > 18"
    assert rule.error_messages == ["Must be adult"]


def test_catch_block_becomes_error_handling_rule(tmp_path):
    az = _project(tmp_path, {"Net.kt": "fun run() { try { call() } catch (e: IOException) { log(e) } }\n"})
    az.analyze()
    rule = next(r for r in az.analysis.business_rules if r.description == "Handle IOException")
    assert rule.type == BusinessRuleType.ERROR_HANDLING
    assert rule.condition == "When IOException occurs"


# --------------------------------------------------------------------------- #
# State machines from sealed classes
# --------------------------------------------------------------------------- #
def test_state_machine_extracted_from_sealed_class(tmp_path):
    az = _project(
        tmp_path,
        {
            "Payment.kt": (
                "sealed class PaymentState {\n"
                "  class Pending : PaymentState()\n"
                "  class Completed : PaymentState()\n"
                "  class Failed : PaymentState()\n"
                "  // transition: Pending -> next = Completed\n"
                "}\n"
            )
        },
    )
    az.extract_state_machines()
    sm = next(s for s in az.analysis.state_machines if s.name == "PaymentState")
    assert sm.states == ["Pending", "Completed", "Failed"]
    assert sm.initial_state == "Pending"
    assert set(sm.transitions.keys()) == {"Pending", "Completed", "Failed"}
    # The comment "Pending -> next = Completed" is a same-line assignment the
    # transition finder picks up.
    assert "Completed" in sm.transitions["Pending"]


def test_sealed_class_with_single_variant_is_not_a_state_machine(tmp_path):
    # `len(states) > 1` is required.
    az = _project(tmp_path, {"One.kt": ("sealed class OneState {\n  class Only : OneState()\n}\n")})
    az.extract_state_machines()
    assert az.analysis.state_machines == []


# --------------------------------------------------------------------------- #
# Retrofit API contracts
# --------------------------------------------------------------------------- #
def test_api_contracts_from_retrofit_interface(tmp_path):
    az = _project(
        tmp_path,
        {
            "Api.kt": (
                "interface Api {\n"
                '  @GET("/users") suspend fun getUsers(): List<User>\n'
                "  // returns 404 if unknown, Authorization header required\n"
                '  @POST("/login") suspend fun login(@Body req: LoginRequest): Token\n'
                "}\n"
            )
        },
    )
    az.generate_api_contracts()
    by_endpoint = {c.endpoint: c for c in az.analysis.api_contracts}

    get_users = by_endpoint["/users"]
    assert get_users.method == "GET"
    assert get_users.response_schema == {"type": "List<User>"}
    assert get_users.request_schema == {}

    login = by_endpoint["/login"]
    assert login.method == "POST"
    assert login.response_schema == {"type": "Token"}
    assert login.request_schema["body"] == {"req": "LoginRequest"}
    # "Authorization" appears in the file -> auth flagged as Bearer Token.
    assert login.authentication == "Bearer Token"
    # 404 is picked up from the surrounding context.
    assert any(err["code"] == "404" for err in login.error_responses)


def test_generate_api_contracts_no_annotations(tmp_path):
    az = _project(tmp_path, {"Plain.kt": "class Plain { fun helper(): Int = 1 }\n"})
    az.generate_api_contracts()
    assert az.analysis.api_contracts == []


# --------------------------------------------------------------------------- #
# Full analyze() integration
# --------------------------------------------------------------------------- #
def test_analyze_populates_multiple_categories(tmp_path):
    az = _project(
        tmp_path,
        {
            "CheckoutViewModel.kt": "class CheckoutViewModel {\n  fun pay() {}\n}\n",
            "OrderRepository.kt": "interface OrderRepository {\n  suspend fun placeOrder(o: Order): Receipt\n}\n",
            "models/Order.kt": "data class Order(val id: Int, val total: Double)\n",
            "mock/MockData.kt": "val MockData.orders by lazy { (1..5) }\n",
        },
    )
    az.analyze()
    assert any(f.name == "Checkout" for f in az.analysis.user_flows)
    assert any(r.related_entities == ["Receipt"] for r in az.analysis.business_rules)
    assert any(m.name == "Order" for m in az.analysis.data_models)
    assert az.analysis.mock_data["orders"]["count"] == 5


def test_analyze_on_empty_project_is_noop(tmp_path):
    az = AndroidBusinessAnalyzer(tmp_path, BusinessLogicAnalysis())
    az.analyze()
    assert az.analysis.user_flows == []
    assert az.analysis.business_rules == []
    assert az.analysis.data_models == []
    assert az.analysis.mock_data == {}


# --------------------------------------------------------------------------- #
# Pre-populated shared analysis is preserved (analyzer appends, never resets)
# --------------------------------------------------------------------------- #
def test_analyzer_appends_to_shared_analysis(tmp_path):
    shared = BusinessLogicAnalysis()
    shared.user_flows.append(
        UserFlow(name="Existing", description="d", steps=[], entry_point="E", success_outcome="ok")
    )
    shared.business_rules.append(
        BusinessRule(type=BusinessRuleType.VALIDATION, description="pre", condition="c", source_file="s")
    )
    shared.edge_cases.append(EdgeCase(type="null", description="pre-edge"))
    (tmp_path / "LoginViewModel.kt").write_text("class LoginViewModel {\n  fun signIn() {}\n}\n")

    AndroidBusinessAnalyzer(tmp_path, shared).analyze()

    assert any(f.name == "Existing" for f in shared.user_flows)
    assert any(f.name == "Login" for f in shared.user_flows)
    assert any(r.description == "pre" for r in shared.business_rules)
