"""
Python + pytest + Appium emitter (imperative style).

Renders a runnable pytest module. Self-healing is expressed in the generated
code as a ``_find`` helper that walks the primary locator then ranked
fallbacks. The IR->Python locator mapping lives in :mod:`_python_common` and is
shared with the BDD emitter so the two styles never drift.
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters._naming import snake
from framework.codegen.emitters._python_common import by_value, keycode, py_str
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import Selector, TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


def _data_key(selector: Selector) -> str:
    """A stable TEST_DATA key for an input field — its human field name, snake_cased
    ('Email address' -> email_address), falling back to the locator value."""
    return snake(getattr(selector, "description", "") or getattr(selector, "value", "") or "input")


class PythonPytestEmitter(Emitter):
    target_id = "python_pytest"

    def _register_filters(self) -> None:
        self.env.filters["by_value"] = by_value
        self.env.filters["py_str"] = py_str
        self.env.filters["keycode"] = keycode
        self.env.filters["data_key"] = _data_key

    def emit(self, model: TestModel) -> Dict[str, str]:
        template = self.env.get_template("test_file.py.j2")
        content = template.render(model=model)
        return {f"test_{snake(model.name)}.py": content}


register(
    Target(
        id="python_pytest",
        language=Language.PYTHON,
        runner="pytest",
        binding="appium",
        file_extension=".py",
        description="Python + pytest + Appium, imperative style (flagship target)",
    ),
    PythonPytestEmitter,
)
