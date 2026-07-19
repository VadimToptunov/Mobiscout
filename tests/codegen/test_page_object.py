"""Tests for the codegen Page Object emitter (framework.codegen.page_object)."""

import py_compile

from framework.codegen.page_object import build_page_object, emit_page_objects
from framework.codegen.ir import SelectorStrategy
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


def test_build_page_object_ranks_and_names():
    po = build_page_object(_app_model().screens["login"])
    assert po.class_name == "LoginScreenPage"
    assert [f.name for f in po.fields] == ["username_field", "login_btn"]
    # test_id (0.95) outranks the parsed android id
    assert po.fields[0].selector.strategy is SelectorStrategy.ACCESSIBILITY_ID
    assert po.fields[0].selector.fallbacks  # self-healing fallback preserved


def test_emit_page_objects_compiles(tmp_path):
    out = emit_page_objects(_app_model())
    assert list(out) == ["login_screen_page.py"]
    content = out["login_screen_page.py"]
    # key structure: class, self-healing find, LOCATORS registry, accessors
    assert "class LoginScreenPage:" in content
    assert "def _find(self, name):" in content
    assert "LOCATORS = {" in content
    assert "def username_field(self):" in content and "def login_btn(self):" in content
    # P3: element lookups are condition-based (WebDriverWait), never a global
    # implicit wait or a fixed sleep — those are the flakiness anti-patterns.
    assert "WebDriverWait" in content
    assert "implicitly_wait" not in content and "time.sleep" not in content
    # and it must be valid Python
    f = tmp_path / "login_screen_page.py"
    f.write_text(content, encoding="utf-8", newline="\n")
    py_compile.compile(str(f), doraise=True)
