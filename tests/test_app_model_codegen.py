"""
Tests for the AppModel -> codegen path: the pydantic app model adapter and the
`mobiscout generate tests` CLI command that wires codegen into the CLI.
"""

import py_compile
from pathlib import Path

from click.testing import CliRunner

from framework.codegen.app_model_adapter import build_smoke_model
from framework.codegen.ir import ActionType, AssertionType, SelectorStrategy
from framework.cli.generate_commands import generate
from framework.model.app_model import AppModel, AppModelMeta
from framework.model.element import Element
from framework.model.enums import ElementType, Platform
from framework.model.screen import Screen
from framework.model.selector import Selector


def _app_model() -> AppModel:
    return AppModel(
        meta=AppModelMeta(app_version="1.0.0", platform=Platform.ANDROID),
        screens={
            "login": Screen(
                name="LoginScreen",
                elements=[
                    Element(
                        id="username_field",
                        type=ElementType.INPUT,
                        selector=Selector(android="id:com.app:id/username", test_id="username"),
                    ),
                    Element(
                        id="login_btn",
                        type=ElementType.BUTTON,
                        selector=Selector(android="accessibility:login", xpath="//button[1]"),
                    ),
                ],
            )
        },
    )


class TestAppModelAdapter:
    def test_builds_one_case_per_screen(self):
        model = build_smoke_model(_app_model(), app_package="com.app")
        assert [c.name for c in model.cases] == ["loginscreen"]
        steps = model.cases[0].steps
        assert steps[0].action is ActionType.LAUNCH
        assert all(s.assertion is AssertionType.VISIBLE for s in steps[1:])

    def test_test_id_becomes_accessibility_primary_with_fallback(self):
        model = build_smoke_model(_app_model(), app_package="com.app")
        username_step = model.cases[0].steps[1]
        sel = username_step.selector
        # test_id (0.95) outranks the parsed android id (0.90)
        assert sel.strategy is SelectorStrategy.ACCESSIBILITY_ID
        assert sel.value == "username"
        assert [(f.strategy, f.value) for f in sel.fallbacks] == [(SelectorStrategy.ID, "com.app:id/username")]

    def test_locator_prefix_parsing_and_xpath_fallback(self):
        model = build_smoke_model(_app_model(), app_package="com.app")
        btn = model.cases[0].steps[2].selector
        assert btn.strategy is SelectorStrategy.ACCESSIBILITY_ID and btn.value == "login"
        assert btn.fallbacks[0].strategy is SelectorStrategy.XPATH


class TestGenerateTestsCommand:
    YAML = """
meta:
  app_version: "1.0.0"
  platform: android
screens:
  login:
    name: LoginScreen
    elements:
      - id: username_field
        type: input
        selector:
          android: "id:com.app:id/username"
          test_id: username
      - id: login_btn
        type: button
        selector:
          android: "accessibility:login"
"""

    def test_generates_compilable_python(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("app.yaml").write_text(self.YAML)
            result = runner.invoke(
                generate,
                [
                    "tests",
                    "--model",
                    "app.yaml",
                    "--app-package",
                    "com.app",
                    "--target",
                    "python_pytest",
                    "--output",
                    "out",
                ],
            )
            assert result.exit_code == 0, result.output
            generated = list(Path("out").rglob("*.py"))
            assert generated, "no python files generated"
            for f in generated:
                py_compile.compile(str(f), doraise=True)

    def test_list_targets(self):
        result = CliRunner().invoke(generate, ["tests", "--list-targets", "--model", __file__, "--app-package", "x"])
        assert result.exit_code == 0
        assert "python_pytest" in result.output and "kotlin_espresso" in result.output

    def test_unknown_target_rejected(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("app.yaml").write_text(self.YAML)
            result = runner.invoke(
                generate,
                ["tests", "--model", "app.yaml", "--app-package", "com.app", "--target", "cobol"],
            )
            assert result.exit_code != 0
            assert "Unknown target" in result.output
