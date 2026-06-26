"""
JavaScript + WebdriverIO + Appium emitter (imperative style, Mocha specs).

Third language target. Like the others it consumes the same TestModel; only the
template and the IR->WebdriverIO locator mapping (:mod:`_js_common`) differ.
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters._js_common import js_str, selector_array
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


def _kebab(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("-")
        out.append(ch.lower())
    return "".join(out).replace(" ", "-").replace("_", "-")


class JsWebdriverIOEmitter(Emitter):
    target_id = "js_webdriverio"

    def _register_filters(self) -> None:
        self.env.filters["selector_array"] = selector_array
        self.env.filters["js_str"] = js_str

    def emit(self, model: TestModel) -> Dict[str, str]:
        content = self.env.get_template("test_file.spec.js.j2").render(model=model)
        return {f"{_kebab(model.name)}.spec.js": content}


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
