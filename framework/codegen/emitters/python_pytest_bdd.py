"""
Python + pytest-bdd + Appium emitter (BDD style).

Emits two artifacts from one IR model:
  * a clean, language-agnostic Gherkin ``.feature`` file (shared with every
    other BDD emitter via _bdd_common — byte-identical across languages);
  * a step-definition module whose generic, reusable steps resolve targets
    through a LOCATORS registry (primary + fallbacks), keeping self-healing in
    the glue and the feature abstract.

The IR->Python locator mapping is shared with the imperative emitter via
:mod:`_python_common`, so both output styles stay consistent.
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters._bdd_common import render_feature
from framework.codegen.emitters._naming import snake
from framework.codegen.emitters._python_common import collect_locators, py_str
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import TestModel
from framework.codegen.keys import as_python_dict_literal
from framework.codegen.targets import Target, register
from framework.core.engine import Language


class PythonPytestBddEmitter(Emitter):
    target_id = "python_pytest_bdd"

    def _register_filters(self) -> None:
        self.env.filters["py_str"] = py_str

    def emit(self, model: TestModel) -> Dict[str, str]:
        slug = snake(model.name)
        steps = self.env.get_template("steps.py.j2").render(
            model=model,
            feature_file=f"{slug}.feature",
            locators=collect_locators(model),
            # Keycode table embedded in the generated glue, from the one source.
            keycodes_literal=as_python_dict_literal(),
        )
        return {
            f"features/{slug}.feature": render_feature(model),
            f"test_{slug}_bdd.py": steps,
        }


register(
    Target(
        id="python_pytest_bdd",
        language=Language.PYTHON,
        runner="pytest-bdd",
        binding="appium",
        file_extension=".py",
        description="Python + pytest-bdd + Appium, BDD/Gherkin style",
    ),
    PythonPytestBddEmitter,
)
