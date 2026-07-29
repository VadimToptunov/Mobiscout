"""
Kotlin + JUnit5 + Appium emitter (imperative style).

Fourth language, Appium flavour: Kotlin drives the same Appium Java client as
the Java target, so it slots straight into the IR with no model changes — only
the template and the IR->Kotlin locator mapping (:mod:`_kotlin_common`) differ.
(A separate Espresso flavour, which is NOT WebDriver, is handled elsewhere.)
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters._kotlin_common import by_array, by_expr, kotlin_str
from framework.codegen.emitters._naming import ua_escape
from framework.codegen.emitters._naming import camel, pascal
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


class KotlinAppiumEmitter(Emitter):
    target_id = "kotlin_appium"

    #: platform of the model being emitted; read by the platform-aware locator
    #: filters. Set per-emit so a TEXT selector renders correctly for iOS.
    _platform: str = "android"

    def _register_filters(self) -> None:
        # by_expr/by_array are platform-aware (TEXT -> androidUIAutomator on
        # Android, xpath-by-label on iOS); bind the model's platform at emit time.
        self.env.filters["by_expr"] = lambda sel: by_expr(sel, self._platform)
        self.env.filters["ua_escape"] = ua_escape
        self.env.filters["by_array"] = lambda sel: by_array(sel, self._platform)
        self.env.filters["kotlin_str"] = kotlin_str
        self.env.filters["camel"] = camel

    def emit(self, model: TestModel) -> Dict[str, str]:
        self._platform = model.platform.value
        class_name = pascal(model.name)
        content = self.env.get_template("test_file.kt.j2").render(model=model, class_name=class_name)
        return {f"{class_name}.kt": content}


register(
    Target(
        id="kotlin_appium",
        language=Language.KOTLIN,
        runner="junit5",
        binding="appium",
        file_extension=".kt",
        description="Kotlin + JUnit5 + Appium, imperative style",
    ),
    KotlinAppiumEmitter,
)
