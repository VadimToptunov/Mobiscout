"""IOSBusinessAnalyzer mines business logic from Swift/SwiftUI sources — views &
flows, ViewModels, Codable models, mock data, business rules, state machines and
URLSession API contracts. Pure text analysis over a project dir; previously 0%."""

from framework.analyzers.business_logic_analyzer import BusinessLogicAnalysis
from framework.analyzers.ios_business_analyzer import IOSBusinessAnalyzer


def _project(tmp_path, files: dict):
    for name, content in files.items():
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
    return IOSBusinessAnalyzer(tmp_path, BusinessLogicAnalysis())


def test_swiftui_view_button_becomes_user_flow(tmp_path):
    az = _project(
        tmp_path,
        {
            "LoginView.swift": (
                "struct LoginView: View {\n"
                "  var body: some View {\n"
                '    Button("Sign in") { viewModel.login() }\n'
                "  }\n}\n"
            )
        },
    )
    az.analyze()
    flows = az.analysis.user_flows
    assert any(f.entry_point == "LoginView" for f in flows)
    assert any("Tap Sign in" in step for f in flows for step in f.steps)


def test_viewmodel_methods_become_a_flow(tmp_path):
    az = _project(
        tmp_path,
        {
            "AuthViewModel.swift": (
                "class AuthViewModel: ObservableObject {\n" "  func login() {}\n" "  func logout() {}\n" "}\n"
            )
        },
    )
    az.analyze()
    vm = next(f for f in az.analysis.user_flows if f.entry_point == "AuthViewModelScreen")
    assert "User login" in vm.steps and "User logout" in vm.steps


def test_codable_model_fields_extracted(tmp_path):
    az = _project(
        tmp_path,
        {
            "Models/Account.swift": (
                "struct Account: Codable {\n"
                "  let id: Int\n"
                "  var balance: Double\n"
                "  let currency: String\n"
                "}\n"
            )
        },
    )
    az.analyze()
    model = next(m for m in az.analysis.data_models if m.name == "Account")
    assert model.fields["id"] == "Int" and model.fields["balance"] == "Double"


def test_business_rule_from_todo_comment(tmp_path):
    az = _project(
        tmp_path,
        {"Rules.swift": "// TODO: validate the IBAN before transfer\nfunc transfer() {}\n"},
    )
    az.analyze()
    assert any("IBAN" in r.description for r in az.analysis.business_rules)


def test_mock_static_array_counted(tmp_path):
    az = _project(
        tmp_path,
        {
            "MockData.swift": (
                "enum MockData {\n"
                "  static let accounts: [Account] = [\n"
                "    Account(id: 1), Account(id: 2), Account(id: 3)\n"
                "  ]\n}\n"
            )
        },
    )
    az.analyze()
    assert az.analysis.mock_data["accounts"]["count"] == 3
    assert az.analysis.mock_data["accounts"]["type"] == "Account"


def test_state_machine_from_enum(tmp_path):
    az = _project(
        tmp_path,
        {
            "Session.swift": (
                "enum SessionState {\n" "  case loggedOut\n" "  case authenticating\n" "  case loggedIn\n" "}\n"
            )
        },
    )
    az.extract_state_machines()
    sm = next(s for s in az.analysis.state_machines if s.name == "SessionState")
    assert set(sm.states) == {"loggedOut", "authenticating", "loggedIn"}
    assert sm.initial_state == "loggedOut"


def test_api_contract_from_urlsession(tmp_path):
    az = _project(
        tmp_path,
        {
            "API.swift": (
                'let url = URL(string: "https://api.bank.com/v1/transfer")\n'
                "var request = URLRequest(url: url!)\n"
                'request.httpMethod = "POST"\n'
            )
        },
    )
    az.generate_api_contracts()
    contracts = az.analysis.api_contracts
    assert any("api.bank.com/v1/transfer" in c.endpoint for c in contracts)
    assert any(c.method == "POST" for c in contracts)


def test_analyze_empty_project_is_safe(tmp_path):
    az = IOSBusinessAnalyzer(tmp_path, BusinessLogicAnalysis())
    az.analyze()  # no .swift files
    assert az.analysis.user_flows == [] and az.analysis.data_models == []
