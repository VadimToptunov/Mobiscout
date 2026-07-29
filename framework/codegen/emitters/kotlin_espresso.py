"""
Kotlin + Espresso emitter (Android instrumented tests, BDD-free).

The Espresso flavour of Kotlin. Unlike every other target so far, Espresso is
NOT WebDriver/Appium: tests run on-device in the androidTest source set against
the real view hierarchy. The IR is reused unchanged, but this emitter maps it
onto a different surface and honestly handles the concepts Espresso lacks:

  * LAUNCH    -> an ActivityScenarioRule (not a runtime call)
  * XPATH     -> no equivalent; the step is annotated as skipped
  * fallbacks -> not expressed at runtime; the primary matcher is used
  * WAIT      -> Espresso auto-synchronizes; omitted
  * BACK      -> Espresso.pressBack()

Per-step rendering is done here (in Python) because of these special cases; the
template just lays out the class and emits the prepared lines.
"""

from __future__ import annotations

from typing import Dict, List

from framework.codegen.emitters._espresso_common import activity_class, matcher_expr
from framework.codegen.emitters._kotlin_common import kotlin_str
from framework.codegen.emitters._naming import camel, pascal
from framework.codegen.emitters.base import Emitter
from framework.codegen.ir import ActionType, AssertionType, TestCase, TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language


def _render_case(case: TestCase) -> List[str]:
    """Render a case's steps to Espresso Kotlin statements (no indentation)."""
    lines: List[str] = []
    for step in case.steps:
        if step.description:
            lines.append(f"// {step.description}")
        a = step.action
        if a is ActionType.LAUNCH:
            lines.append("// (app launched by ActivityScenarioRule above)")
        elif a is ActionType.BACK:
            lines.append("pressBack()")
        elif a is ActionType.SWIPE:
            swipe = {
                "up": "swipeUp",
                "down": "swipeDown",
                "left": "swipeLeft",
                "right": "swipeRight",
            }.get((step.direction or "up").lower(), "swipeUp")
            lines.append(f"onView(isRoot()).perform({swipe}())")
        elif a is ActionType.WAIT:
            lines.append("// (Espresso auto-synchronizes with the UI thread; explicit wait omitted)")
        elif a in (ActionType.TAP, ActionType.TYPE):
            matcher = matcher_expr(step.selector)
            if matcher is None:
                lines.append(f"// SKIPPED — Espresso has no XPath locator for this {a.value}")
            elif a is ActionType.TAP:
                lines.append(f"onView({matcher}).perform(click())")
            else:
                lines.append(f"onView({matcher}).perform(typeText({kotlin_str(step.text)}), closeSoftKeyboard())")
        elif a is ActionType.ASSERT:
            matcher = matcher_expr(step.selector)
            if matcher is None:
                lines.append("// SKIPPED — Espresso has no XPath locator for this assertion")
            elif step.assertion is AssertionType.VISIBLE:
                lines.append(f"onView({matcher}).check(matches(isDisplayed()))")
            elif step.assertion is AssertionType.ENABLED:
                lines.append(f"onView({matcher}).check(matches(isEnabled()))")
            elif step.assertion is AssertionType.TEXT_EQUALS:
                lines.append(f"onView({matcher}).check(matches(withText({kotlin_str(step.expected)})))")
    return lines


class KotlinEspressoEmitter(Emitter):
    target_id = "kotlin_espresso"

    def emit(self, model: TestModel) -> Dict[str, str]:
        class_name = f"{pascal(model.name)}Test"
        cases = [{"name": camel(c.name), "lines": _render_case(c)} for c in model.cases]
        content = self.env.get_template("test_file.kt.j2").render(
            model=model,
            class_name=class_name,
            activity=activity_class(model),
            cases=cases,
        )
        return {f"{class_name}.kt": content}


register(
    Target(
        id="kotlin_espresso",
        language=Language.KOTLIN,
        runner="espresso",
        binding="espresso",
        file_extension=".kt",
        description="Kotlin + Espresso, Android instrumented tests (not WebDriver)",
    ),
    KotlinEspressoEmitter,
)
