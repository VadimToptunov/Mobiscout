"""
Python + pytest + Appium emitter.

Maps the abstract IR onto the Appium Python client (``appium-python-client``)
and renders a runnable pytest module. Self-healing is expressed in the
generated code as a ``_find`` helper that walks the primary locator then the
ranked fallbacks.
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import Selector, SelectorStrategy, TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language

# Abstract strategy -> AppiumBy member used in generated Python code.
_APPIUM_BY = {
    SelectorStrategy.ID: "AppiumBy.ID",
    SelectorStrategy.ACCESSIBILITY_ID: "AppiumBy.ACCESSIBILITY_ID",
    SelectorStrategy.XPATH: "AppiumBy.XPATH",
    SelectorStrategy.CLASS_NAME: "AppiumBy.CLASS_NAME",
    # Android text -> uiautomator selector; readable and stable enough for v1.
    SelectorStrategy.TEXT: "AppiumBy.ANDROID_UIAUTOMATOR",
}


def _py_str(value: str) -> str:
    """Render a Python double-quoted string literal, safely escaped."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _locator_value(sel: Selector) -> str:
    """Produce the locator value string as it should appear in Python."""
    if sel.strategy is SelectorStrategy.TEXT:
        # uiautomator expression for visible text
        return _py_str(f'new UiSelector().text("{sel.value}")')
    return _py_str(sel.value)


def _by_value(sel: Selector) -> str:
    """Render a ``(AppiumBy.X, "value")`` tuple for the _find helper."""
    return f"({_APPIUM_BY[sel.strategy]}, {_locator_value(sel)})"


class PythonPytestEmitter(Emitter):
    target_id = "python_pytest"

    def _register_filters(self) -> None:
        self.env.filters["by_value"] = _by_value
        self.env.filters["py_str"] = _py_str

    def emit(self, model: TestModel) -> Dict[str, str]:
        template = self.env.get_template("test_file.py.j2")
        content = template.render(model=model)
        filename = f"test_{_snake(model.name)}.py"
        return {filename: content}


def _snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out).replace(" ", "_").replace("-", "_")


register(
    Target(
        id="python_pytest",
        language=Language.PYTHON,
        runner="pytest",
        binding="appium",
        file_extension=".py",
        description="Python + pytest + Appium (flagship target)",
    ),
    PythonPytestEmitter,
)
