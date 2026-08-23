"""
Maestro emitter — declarative YAML flows (https://maestro.dev).

Unlike every other target, Maestro is NOT WebDriver/Appium and NOT a programming
language: a test is a YAML *flow* of high-level commands (``tapOn``, ``inputText``,
``assertVisible``) that Maestro runs cross-platform with built-in waiting. The IR is
reused unchanged; this emitter maps it onto Maestro's command vocabulary and is honest
about the few concepts Maestro has no equivalent for.

  * one flow file per test case (``<case>.yaml``), each with an ``appId`` header
  * ID / ACCESSIBILITY_ID -> ``id:``  (Maestro's id matches resource-id / a11y id)
  * TEXT                  -> ``text:``
  * XPATH / CLASS_NAME    -> no equivalent; the step is annotated as skipped
  * WAIT                  -> ``extendedWaitUntil`` (Maestro also auto-waits)
  * fallbacks             -> not expressed; the primary selector is used

Rendering is pure Python (no Jinja template) because Maestro YAML is line-oriented and
the per-command shape varies enough that a template would be less clear than the mapping.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from framework.codegen.emitters._naming import snake
from framework.codegen.ir import ActionType, AssertionType, Selector, SelectorStrategy, Step, TestCase, TestModel
from framework.codegen.targets import Target, register
from framework.core.engine import Language

_SWIPE = {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT"}


def _yaml_str(value: str) -> str:
    """A double-quoted YAML scalar with the minimal escaping Maestro needs."""
    escaped = (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _selector(sel: Optional[Selector]) -> Optional[Tuple[str, str]]:
    """Map an IR selector to a Maestro ``(key, value)`` — ``id`` or ``text``. None when
    Maestro has no equivalent (XPath / class-name), so the caller can skip honestly."""
    if sel is None:
        return None
    if sel.strategy in (SelectorStrategy.ID, SelectorStrategy.ACCESSIBILITY_ID):
        return ("id", sel.value)
    if sel.strategy is SelectorStrategy.TEXT:
        return ("text", sel.value)
    return None


def _selector_block(sel: Optional[Selector], indent: str) -> Optional[List[str]]:
    kv = _selector(sel)
    if kv is None:
        return None
    return [f"{indent}{kv[0]}: {_yaml_str(kv[1])}"]


def _render_step(step: Step) -> List[str]:  # noqa: C901 — one clause per action kind
    """Render one IR step to Maestro YAML command lines (no leading list indent yet)."""
    lines: List[str] = []
    if step.description:
        lines.append(f"# {step.description}")
    a = step.action

    if a is ActionType.LAUNCH:
        lines.append("- launchApp")
    elif a is ActionType.BACK:
        lines.append("- back")
    elif a is ActionType.SWIPE:
        lines.append("- swipe:")
        lines.append(f"    direction: {_SWIPE.get((step.direction or 'up').lower(), 'UP')}")
    elif a is ActionType.DEEP_LINK:
        lines.append("- openLink:")
        lines.append(f"    link: {_yaml_str(step.text or '')}")
    elif a is ActionType.PRESS_KEY:
        lines.append(f"- pressKey: {_yaml_str(step.text or '')}")
    elif a is ActionType.SWITCH_CONTEXT:
        lines.append("# (Maestro operates on the visible view; native/webview context switch not needed)")
    elif a is ActionType.WAIT:
        block = _selector_block(step.selector, "      ")
        if block:
            lines.append("- extendedWaitUntil:")
            lines.append("    visible:")
            lines.extend(block)
            lines.append(f"    timeout: {int((step.timeout or 5) * 1000)}")
        else:
            lines.append("- waitForAnimationToEnd")
    elif a is ActionType.SCROLL_TO:
        block = _selector_block(step.selector, "      ")
        if block:
            lines.append("- scrollUntilVisible:")
            lines.append("    element:")
            lines.extend(block)
        else:
            lines.append(f"# SKIPPED scroll_to — Maestro has no selector for this ({_strat(step.selector)})")
    elif a in (ActionType.TAP, ActionType.LONG_PRESS, ActionType.TYPE):
        lines.extend(_render_target_action(step, a))
    elif a is ActionType.ASSERT:
        lines.extend(_render_assert(step))
    return lines


def _render_target_action(step: Step, a: ActionType) -> List[str]:
    block = _selector_block(step.selector, "    ")
    if block is None:
        return [f"# SKIPPED {a.value} — Maestro has no selector for this ({_strat(step.selector)})"]
    verb = {ActionType.TAP: "tapOn", ActionType.LONG_PRESS: "longPressOn", ActionType.TYPE: "tapOn"}[a]
    lines = [f"- {verb}:", *block]
    if a is ActionType.TYPE:
        lines.append(f"- inputText: {_yaml_str(step.text or '')}")
    return lines


def _render_assert(step: Step) -> List[str]:
    if step.assertion is AssertionType.TEXT_EQUALS:
        return ["- assertVisible:", f"    text: {_yaml_str(step.expected or '')}"]
    block = _selector_block(step.selector, "    ")
    if block is None:
        return [f"# SKIPPED assert — Maestro has no selector for this ({_strat(step.selector)})"]
    if step.assertion is AssertionType.NOT_VISIBLE:
        return ["- assertNotVisible:", *block]
    if step.assertion is AssertionType.ENABLED:
        return ["- assertVisible:", *block, "    enabled: true"]
    return ["- assertVisible:", *block]  # VISIBLE (default)


def _strat(sel: Optional[Selector]) -> str:
    return sel.strategy.value if sel else "none"


def _render_case(case: TestCase, app_id: str) -> str:
    header = ["# Generated by Mobiscout — Maestro flow", f"appId: {_yaml_str(app_id)}"]
    if case.description:
        header.append(f"# {case.description}")
    header.append("---")
    body: List[str] = []
    for step in case.steps:
        body.extend(_render_step(step))
    return "\n".join(header + body) + "\n"


class MaestroEmitter:
    """Emit one Maestro YAML flow per test case. Not template-backed — see module docstring."""

    target_id = "maestro"

    def emit(self, model: TestModel) -> Dict[str, str]:
        app_id = model.app_package
        files: Dict[str, str] = {}
        seen: Dict[str, int] = {}
        for case in model.cases:
            name = snake(case.name) or "flow"
            # De-dupe flow filenames deterministically if two cases snake to the same stem.
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 0
            files[f"{name}.yaml"] = _render_case(case, app_id)
        return files


register(
    Target(
        id="maestro",
        language=Language.YAML,
        runner="maestro",
        binding="maestro",
        file_extension=".yaml",
        description="Maestro YAML flows (cross-platform, no Appium/WebDriver)",
    ),
    MaestroEmitter,
)
