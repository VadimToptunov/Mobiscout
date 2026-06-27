"""
Java + Cucumber-JVM + Appium emitter (BDD style).

Fills the Java x BDD cell of the target matrix. Shares the Gherkin feature with
every other BDD target (via _bdd_common) and the IR->Java locator mapping with
the imperative Java target (via _java_common) — so the feature is identical
across languages and the locators are identical across Java styles.
"""

from __future__ import annotations

from typing import Dict

from framework.codegen.emitters._bdd_common import collect_targets, render_feature
from framework.codegen.emitters._java_common import by_list, java_str
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


def _pascal(name: str) -> str:
    parts = [p for p in name.replace("-", "_").replace(" ", "_").split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Generated"


class JavaCucumberEmitter(Emitter):
    target_id = "java_cucumber"

    def _register_filters(self) -> None:
        self.env.filters["java_str"] = java_str

    def emit(self, model: TestModel) -> Dict[str, str]:
        base = _pascal(model.name)
        # (registry key, Java By[] literal of primary + fallbacks)
        locators = [(key, by_list(sel)) for key, sel in collect_targets(model)]
        steps = self.env.get_template("steps.java.j2").render(model=model, class_name=f"{base}Steps", locators=locators)
        return {
            f"{base}.feature": render_feature(model),
            f"{base}Steps.java": steps,
        }


register(
    Target(
        id="java_cucumber",
        language=Language.JAVA,
        runner="cucumber",
        binding="appium",
        file_extension=".java",
        description="Java + Cucumber-JVM + Appium, BDD/Gherkin style",
    ),
    JavaCucumberEmitter,
)
