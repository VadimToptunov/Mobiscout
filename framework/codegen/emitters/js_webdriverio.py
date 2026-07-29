"""
JavaScript + WebdriverIO + Appium emitter (imperative style, Mocha specs).

Third language target. Like the others it consumes the same TestModel; only the
template and the IR->WebdriverIO locator mapping (:mod:`_js_common`) differ.
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters._js_common import js_str, selector_array
from framework.codegen.emitters._naming import ua_escape
from framework.codegen.emitters._naming import kebab
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


class JsWebdriverIOEmitter(Emitter):
    target_id = "js_webdriverio"

    #: platform of the model being emitted; read by the platform-aware locator
    #: filter. Set per-emit so a TEXT selector renders correctly for iOS.
    _platform: str = "android"

    def _register_filters(self) -> None:
        from framework.codegen.emitters._python_common import keycode

        # selector_array is platform-aware (TEXT -> uiAutomator on Android,
        # xpath-by-label on iOS); bind the model's platform at emit time.
        self.env.filters["selector_array"] = lambda sel: selector_array(sel, self._platform)
        self.env.filters["ua_escape"] = ua_escape
        self.env.filters["js_str"] = js_str
        self.env.filters["keycode"] = keycode

    def emit(self, model: TestModel) -> Dict[str, str]:
        self._platform = model.platform.value
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
