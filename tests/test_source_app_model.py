"""Path A: app SOURCE → UI Appium tests. The Android analyzer discovers
screens/elements; this bridges them to an AppModel so `generate tests --source`
produces runnable UI smoke tests from the app's own code."""

import py_compile
from types import SimpleNamespace

from framework.codegen.source_app_model import analysis_to_app_model, source_app_model
from framework.model.enums import ElementType


def _ui(id, type, screen, test_tag=None, content_description=None, text=None):
    return SimpleNamespace(
        id=id, type=type, screen=screen, test_tag=test_tag, content_description=content_description, text=text
    )


def test_analysis_maps_screens_and_element_locators():
    result = SimpleNamespace(
        screens=[SimpleNamespace(name="Login")],
        ui_elements=[
            _ui("username", "TextField", "Login", test_tag="username_field"),
            _ui("greeting", "Text", "Login", content_description="Welcome"),
            _ui("logo", "Image", "Login"),  # no locator -> dropped
        ],
    )
    app_model = analysis_to_app_model(result)
    login = app_model.screens["Login"]
    assert {e.id for e in login.elements} == {"username", "greeting"}  # logo dropped
    types = {e.id: e.type for e in login.elements}
    assert types["username"] == ElementType.INPUT and types["greeting"] == ElementType.TEXT
    # content-description becomes the accessibility id; testTag becomes a resource id.
    by_id = {e.id: e for e in login.elements}
    assert by_id["greeting"].selector.test_id == "Welcome"
    assert by_id["username"].selector.android == "id:username_field"


def test_source_to_runnable_ui_tests_end_to_end(tmp_path):
    """The headline: real Compose source → an AppModel → a runnable pytest that
    launches and asserts the screen's elements are visible, and compiles."""
    (tmp_path / "LoginScreen.kt").write_text(
        """
        @Composable
        fun LoginScreen() {
            Column {
                TextField(value = user, onValueChange = {}, modifier = Modifier.testTag("username_field"))
                Button(onClick = {}, modifier = Modifier.testTag("login_button")) { Text("Log in") }
            }
        }
        """,
        encoding="utf-8",
    )

    from framework.codegen import get_emitter
    from framework.codegen.app_model_adapter import build_smoke_model

    app_model = source_app_model(str(tmp_path))
    assert "LoginScreen" in app_model.screens
    assert app_model.screens["LoginScreen"].elements  # elements discovered

    test_model = build_smoke_model(app_model, app_package="com.example.app", suite_name="SourceSmoke")
    assert test_model.cases, "no test cases from source"

    src = next(iter(get_emitter("python_pytest").emit(test_model).values()))
    assert "login_button" in src and "is_displayed()" in src  # asserts the element is visible
    out = tmp_path / "test_source_smoke.py"
    out.write_text(src, encoding="utf-8", newline="\n")
    py_compile.compile(str(out), doraise=True)


def test_generate_tests_source_cli_end_to_end(tmp_path):
    from click.testing import CliRunner

    from framework.cli.generate_commands import generate

    (tmp_path / "HomeScreen.kt").write_text(
        '@Composable\nfun HomeScreen() { Button(modifier = Modifier.testTag("pay_button")) {} }\n',
        encoding="utf-8",
    )
    out_dir = tmp_path / "gen"
    result = CliRunner().invoke(
        generate,
        ["tests", "--source", str(tmp_path), "--app-package", "com.example.app", "--output", str(out_dir)],
    )
    assert result.exit_code == 0, result.output
    generated = list(out_dir.rglob("test_*.py"))
    assert generated, "no test files written"
    assert "pay_button" in generated[0].read_text(encoding="utf-8")
