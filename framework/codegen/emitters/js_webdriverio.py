"""
JavaScript + WebdriverIO + Appium emitter (imperative style, Mocha specs).

Third language target. Like the others it consumes the same TestModel; only the
template and the IR->WebdriverIO locator mapping (:mod:`_js_common`) differ.
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters._js_common import js_str, selector_array
from framework.codegen.emitters._naming import kebab
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


class JsWebdriverIOEmitter(Emitter):
    target_id = "js_webdriverio"

    def _register_filters(self) -> None:
        from framework.codegen.emitters._python_common import keycode

        self.env.filters["selector_array"] = selector_array
        self.env.filters["js_str"] = js_str
        self.env.filters["keycode"] = keycode

    def emit(self, model: TestModel) -> Dict[str, str]:
        content = self.env.get_template("test_file.spec.js.j2").render(model=model)
        return {f"{kebab(model.name)}.spec.js": content}


register(
    Target(
        id="js_webdriverio",
        language=Language.JAVASCRIPT,
        runner="webdriverio",
        binding="appium",
        file_extension=".js",
        description="JavaScript + WebdriverIO + Appium, imperative style (Mocha)",
    ),
    JsWebdriverIOEmitter,
)
