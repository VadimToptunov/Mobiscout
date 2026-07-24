"""
Java + TestNG + Appium emitter (imperative style).

Proves the IR is genuinely language-agnostic: it consumes the exact same
TestModel as the Python target, only the template and the IR->Java locator
mapping (:mod:`_java_common`) differ.
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters._java_common import by_array, by_expr, java_str
from framework.codegen.emitters._naming import ua_escape
from framework.codegen.emitters._naming import camel, pascal
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


class JavaTestNGEmitter(Emitter):
    target_id = "java_testng"

    def _register_filters(self) -> None:
        self.env.filters["by_expr"] = by_expr
        self.env.filters["ua_escape"] = ua_escape
        self.env.filters["by_array"] = by_array
        self.env.filters["java_str"] = java_str
        self.env.filters["camel"] = camel

    def emit(self, model: TestModel) -> Dict[str, str]:
        class_name = pascal(model.name)
        content = self.env.get_template("test_file.java.j2").render(model=model, class_name=class_name)
        return {f"{class_name}.java": content}


register(
    Target(
        id="java_testng",
        language=Language.JAVA,
        runner="testng",
        binding="appium",
        file_extension=".java",
        description="Java + TestNG + Appium, imperative style",
    ),
    JavaTestNGEmitter,
)
