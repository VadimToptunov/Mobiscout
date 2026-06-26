"""
Python + pytest-bdd + Appium emitter (BDD style).

Emits two artifacts from one IR model:
  * a clean, language-agnostic Gherkin ``.feature`` file (one Scenario per
    TestCase), referencing elements by friendly target name only;
  * a step-definition module whose generic, reusable steps resolve targets
    through a LOCATORS registry (primary + fallbacks) — so the feature stays
    abstract while self-healing lives in the glue.

The IR->Python locator mapping is shared with the imperative emitter via
:mod:`_python_common`, so both output styles stay consistent.
"""

from __future__ import annotations

from typing import Dict, List

from framework.codegen.emitters._python_common import collect_locators, py_str, target_key
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import ActionType, AssertionType, Step, TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


def _snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out).replace(" ", "_").replace("-", "_")


# Which Gherkin clause an action belongs to. Consecutive steps in the same
# clause render as "And" for readability.
_CLAUSE = {
    ActionType.LAUNCH: "Given",
    ActionType.TAP: "When",
    ActionType.TYPE: "When",
    ActionType.SWIPE: "When",
    ActionType.WAIT: "When",
    ActionType.BACK: "When",
    ActionType.ASSERT: "Then",
}


def _phrase(step: Step) -> str:
    """The Gherkin step text — canonical so it matches the step-def parser."""
    a = step.action
    if a is ActionType.LAUNCH:
        return "the app is launched"
    if a is ActionType.TYPE:
        return f'I enter "{step.text}" into "{target_key(step.selector)}"'
    if a is ActionType.TAP:
        return f'I tap "{target_key(step.selector)}"'
    if a is ActionType.WAIT:
        return f"I wait {int(step.timeout or 5)} seconds"
    if a is ActionType.BACK:
        return "I press back"
    if a is ActionType.ASSERT:
        key = target_key(step.selector)
        if step.assertion is AssertionType.VISIBLE:
            return f'"{key}" is visible'
        if step.assertion is AssertionType.TEXT_EQUALS:
            return f'"{key}" text is "{step.expected}"'
        if step.assertion is AssertionType.ENABLED:
            return f'"{key}" is enabled'
    raise ValueError(f"Unsupported step for BDD: {a} / {step.assertion}")


def _scenario_lines(steps: List[Step]) -> List[Dict[str, str]]:
    """Assign Given/When/Then/And keywords to a case's steps."""
    lines: List[Dict[str, str]] = []
    prev_clause = None
    for step in steps:
        clause = _CLAUSE[step.action]
        keyword = "And" if clause == prev_clause else clause
        lines.append({"keyword": keyword, "phrase": _phrase(step)})
        prev_clause = clause
    return lines


class PythonPytestBddEmitter(Emitter):
    target_id = "python_pytest_bdd"

    def _register_filters(self) -> None:
        self.env.filters["py_str"] = py_str

    def emit(self, model: TestModel) -> Dict[str, str]:
        slug = _snake(model.name)
        scenarios = [
            {
                "name": case.name,
                "title": case.description or case.name,
                "lines": _scenario_lines(case.steps),
            }
            for case in model.cases
        ]
        feature = self.env.get_template("feature.feature.j2").render(
            model=model, scenarios=scenarios
        )
        steps = self.env.get_template("steps.py.j2").render(
            model=model,
            feature_file=f"{slug}.feature",
            locators=collect_locators(model),
        )
        return {
            f"features/{slug}.feature": feature,
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
