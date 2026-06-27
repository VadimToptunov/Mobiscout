"""
JavaScript + Cucumber.js + WebdriverIO emitter (BDD style).

Fills the JS x BDD cell of the target matrix. Shares the Gherkin feature with
every other BDD target (via _bdd_common) and the IR->WebdriverIO locator
mapping with the imperative JS target (via _js_common).
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters._bdd_common import collect_targets, render_feature
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


class JsCucumberEmitter(Emitter):
    target_id = "js_cucumber"

    def _register_filters(self) -> None:
        self.env.filters["js_str"] = js_str

    def emit(self, model: TestModel) -> Dict[str, str]:
        slug = _kebab(model.name)
        # (registry key, JS array literal of primary + fallbacks)
        locators = [(key, selector_array(sel)) for key, sel in collect_targets(model)]
        steps = self.env.get_template("steps.js.j2").render(model=model, locators=locators)
        return {
            f"{slug}.feature": render_feature(model),
            f"{slug}.steps.js": steps,
        }


register(
    Target(
        id="js_cucumber",
        language=Language.JAVASCRIPT,
        runner="cucumber",
        binding="appium",
        file_extension=".js",
        description="JavaScript + Cucumber.js + WebdriverIO, BDD/Gherkin style",
    ),
    JsCucumberEmitter,
)
