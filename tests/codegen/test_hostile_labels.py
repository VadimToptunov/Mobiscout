"""A hostile element label must not break the generated kit.

Real UI text carries newlines (a Compose paragraph, a uiautomator dump that
decoded ``&#10;``), quotes and backslashes, and real screens are titled "2FA
Setup". Every imperative target renders a step description into a *line* comment
and turns a case name into a method name, so an unsanitised label used to emit
Python that doesn't parse, Java/Kotlin that doesn't compile and Maestro YAML that
doesn't scan. These tests build a model with all of it and gate the output.
"""

import ast
import re
import shutil
import subprocess

import pytest
import yaml
from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner

from framework.codegen import available_targets, get_emitter
from framework.codegen.app_model_adapter import build_smoke_model
from framework.codegen.emitters._escape import single_line
from framework.codegen.emitters._naming import camel, pascal, snake
from framework.codegen.ir import (
    ActionType,
    AssertionType,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)
from framework.model.app_model import AppModel, AppModelMeta
from framework.model.element import Element
from framework.model.enums import ElementType, Platform
from framework.model.screen import Screen
from framework.model.selector import Selector as ModelSelector

# A label with every character that has broken a target: a double quote, a
# backslash, an interior newline, and non-ASCII text.
NASTY = 'Say "hi"\\now\nsecond line — Überweisung'

TARGET_IDS = [t.id for t in available_targets()]


@pytest.fixture()
def hostile_model() -> TestModel:
    """A model whose labels are hostile and whose case name starts with a digit."""
    sel = Selector(SelectorStrategy.ID, "say_btn", description=NASTY)
    return TestModel(
        name="HostileFlow",
        app_package="com.example.app",
        app_activity="com.example.app.ui.LoginActivity",
        cases=[
            TestCase(
                name="2fa_setup_screen_shows_expected_controls",
                description=f"{NASTY} smoke",
                steps=[
                    Step(ActionType.LAUNCH, description=f"Open {NASTY}"),
                    Step(ActionType.TAP, selector=sel, description=f"Tap {NASTY}"),
                    Step(ActionType.TYPE, selector=sel, text=NASTY, description=f"Enter {NASTY}"),
                    Step(
                        ActionType.ASSERT,
                        selector=sel,
                        assertion=AssertionType.VISIBLE,
                        description=f"{NASTY} is visible",
                    ),
                ],
            )
        ],
    )


def test_single_line_flattens_every_line_break():
    assert single_line("a\nb") == "a b"
    assert single_line("a\r\nb") == "a b"
    assert single_line("a\u2028b") == "a b"  # a LineTerminator in JavaScript
    assert single_line(None) == ""
    assert single_line("clean") == "clean"  # identity for clean values


def test_naming_helpers_never_produce_an_illegal_identifier():
    # A leading digit is illegal in every target language.
    assert camel("2fa_setup") == "_2faSetup"
    assert pascal("2fa setup") == "_2faSetup"
    assert snake("2fa setup") == "_2fa_setup"
    # Punctuation is a word separator, not part of the name.
    assert pascal("Checkout (guest)") == "CheckoutGuest"
    assert snake("btn.confirm") == "btn_confirm"
    # Clean names are untouched.
    assert camel("login_flow") == "loginFlow" and pascal("login_flow") == "LoginFlow"


@pytest.mark.parametrize("target_id", TARGET_IDS)
def test_hostile_labels_do_not_break_any_target(target_id: str, hostile_model: TestModel, tmp_path):
    """Every artifact must still parse/compile for its own language."""
    for path, content in get_emitter(target_id).emit(hostile_model).items():
        f = tmp_path / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8", newline="\n")
        if path.endswith(".py"):
            ast.parse(content)  # raises SyntaxError on a leaked comment line
        elif path.endswith((".yaml", ".yml")):
            list(yaml.safe_load_all(content))
        elif path.endswith(".feature"):
            assert Parser().parse(TokenScanner(content))["feature"] is not None
        elif path.endswith(".js") and shutil.which("node"):
            proc = subprocess.run([shutil.which("node"), "--check", str(f)], capture_output=True, text=True)
            assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("target_id", TARGET_IDS)
def test_no_label_line_escapes_its_comment(target_id: str, hostile_model: TestModel):
    """The label's second line must never land in the file as bare source."""
    for path, content in get_emitter(target_id).emit(hostile_model).items():
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("second line"):
                pytest.fail(f"{target_id}/{path}: label line escaped its comment: {line!r}")


@pytest.mark.parametrize("target_id", TARGET_IDS)
def test_no_method_name_starts_with_a_digit(target_id: str, hostile_model: TestModel):
    """'2FA Setup' is an ordinary screen title; javac/kotlinc reject the method
    name it used to produce, so the whole kit failed to compile."""
    for path, content in get_emitter(target_id).emit(hostile_model).items():
        bad = re.findall(r"(?:public void|fun|def)\s+(\d\w*)\s*\(", content)
        assert not bad, f"{target_id}/{path}: illegal method name(s) {bad}"


def _smoke_app(*names: str) -> AppModel:
    return AppModel(
        meta=AppModelMeta(app_version="1.0.0", platform=Platform.ANDROID),
        screens={
            f"s{i}": Screen(
                name=name,
                elements=[
                    Element(id=f"btn_{i}", type=ElementType.BUTTON, selector=ModelSelector(android=f"id:btn_{i}"))
                ],
            )
            for i, name in enumerate(names)
        },
    )


def test_smoke_case_names_are_unique():
    """Two screens can sanitise to the same case name; the pytest module would
    then define the same test twice (the second silently shadowing the first) and
    the Java class two identically-named methods, which is a compile error."""
    model = build_smoke_model(_smoke_app("Home", "home!"), "com.example.app")
    names = [c.name for c in model.cases]
    assert len(names) == len(set(names)), names
    py_src = next(iter(get_emitter("python_pytest").emit(model).values()))
    defs = [n.name for n in ast.parse(py_src).body if isinstance(n, ast.FunctionDef)]
    assert len(defs) == len(set(defs)), defs
