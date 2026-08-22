"""
Python + pytest + Appium emitter (imperative style).

Renders a runnable pytest module. Self-healing is expressed in the generated
code as a ``_find`` helper that walks the primary locator then ranked
fallbacks. The IR->Python locator mapping lives in :mod:`_python_common` and is
shared with the BDD emitter so the two styles never drift.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from framework.codegen.emitters._naming import snake
from framework.codegen.emitters._naming import ua_escape
from framework.codegen.emitters._python_common import by_value, keycode, py_str
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import Selector, Step, TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


def _field_key(selector: Selector) -> str:
    """The base TEST_DATA key for an input field — its human field name, snake_cased
    ('Email address' -> email_address), falling back to the locator value."""
    return snake(getattr(selector, "description", "") or getattr(selector, "value", "") or "input")


class PythonPytestEmitter(Emitter):
    target_id = "python_pytest"

    #: platform of the model being emitted; read by the platform-aware locator
    #: filter. Set per-emit so a TEXT selector renders correctly for iOS.
    _platform: str = "android"

    def _register_filters(self) -> None:
        # by_value is platform-aware (TEXT -> UiAutomator on Android, XPath-by-label
        # on iOS); bind the current model's platform captured at emit time.
        self.env.filters["by_value"] = lambda sel: by_value(sel, self._platform)
        self.env.filters["ua_escape"] = ua_escape
        self.env.filters["py_str"] = py_str
        self.env.filters["keycode"] = keycode
        # Resolve a type-step to its unique TEST_DATA key (built per emit). Both the
        # TEST_DATA dict and the send_keys body go through this, so they never drift.
        self.env.filters["data_key"] = lambda step: self._assigned[(_field_key(step.selector), step.text or "")]

    def _build_test_data(self, model: TestModel) -> List[Tuple[str, str]]:
        """Assign a unique key to each distinct (field, value) a type step uses, so a
        model carrying both a positive and a negative case on the same field emits two
        entries instead of the negative silently overwriting the positive. Cases that
        type the same value into a field share one key; a differing value gets a numeric
        suffix (email, email_2, …). Returns the (key, value) pairs in first-seen order."""
        self._assigned: Dict[Tuple[str, str], str] = {}
        used: set[str] = set()
        ordered: List[Tuple[str, str]] = []
        for case in model.cases:
            for step in case.steps:
                if step.action.value != "type" or step.selector is None:
                    continue
                base, value = _field_key(step.selector), step.text or ""
                if (base, value) in self._assigned:
                    continue
                key, n = base, 2
                while key in used:
                    key, n = f"{base}_{n}", n + 1
                used.add(key)
                self._assigned[(base, value)] = key
                ordered.append((key, value))
        return ordered

    def emit(self, model: TestModel) -> Dict[str, str]:
        self._platform = model.platform.value
        test_data = self._build_test_data(model)
        template = self.env.get_template("test_file.py.j2")
        content = template.render(model=model, test_data=test_data)
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
