"""
Shared, language-agnostic BDD helpers.

The Gherkin ``.feature`` file is the same regardless of which language the step
definitions are written in — that is the whole point of BDD. So feature
rendering and the friendly target/phrase logic live here and are reused by
every BDD emitter (pytest-bdd, Cucumber-JVM, Cucumber.js), guaranteeing
byte-identical feature files across languages.

Each language emitter only supplies its own step-definition template and its
own rendering of the LOCATORS registry (primary + ranked fallbacks).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from framework.codegen.emitters._naming import snake
from framework.codegen.ir import ActionType, AssertionType, Selector, Step, TestModel


def target_key(sel: Selector) -> str:
    """A friendly, human-facing handle for a selector — the Gherkin target name
    and the LOCATORS registry key. Stable and readable."""
    return sel.description or sel.value


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
    ActionType.LONG_PRESS: "When",
    ActionType.SCROLL_TO: "When",
    ActionType.DEEP_LINK: "When",
    ActionType.PRESS_KEY: "When",
}


def phrase(step: Step, type_param: Optional[str] = None) -> str:
    """The canonical Gherkin step text — must match the step-def parser in every
    language (Cucumber expressions: {string}, {int}).

    ``type_param``: when set, a TYPE step's value is rendered as a
    ``<placeholder>`` so the scenario becomes a data-driven Scenario Outline.
    """
    a = step.action
    if a is ActionType.LAUNCH:
        return "the app is launched"
    if a is ActionType.TYPE:
        value = f"<{type_param}>" if type_param else step.text
        return f'I enter "{value}" into "{target_key(step.selector)}"'
    if a is ActionType.TAP:
        return f'I tap "{target_key(step.selector)}"'
    if a is ActionType.LONG_PRESS:
        return f'I long-press "{target_key(step.selector)}"'
    if a is ActionType.SCROLL_TO:
        return f'I scroll to "{target_key(step.selector)}"'
    if a is ActionType.DEEP_LINK:
        return f'I open the deep link "{step.text}"'
    if a is ActionType.PRESS_KEY:
        return f'I press the "{step.text}" key'
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


def scenario_lines(steps: List[Step]) -> List[Dict[str, str]]:
    """Assign Given/When/Then/And keywords to a case's steps."""
    lines: List[Dict[str, str]] = []
    prev_clause = None
    for step in steps:
        clause = _CLAUSE[step.action]
        keyword = "And" if clause == prev_clause else clause
        lines.append({"keyword": keyword, "phrase": phrase(step)})
        prev_clause = clause
    return lines


def collect_targets(model: TestModel) -> List[Tuple[str, Selector]]:
    """De-duplicated, ordered (target_key, selector) for every selector in the
    model. Each language emitter renders its own LOCATORS registry from this."""
    seen: Dict[str, Selector] = {}
    order: List[str] = []
    for case in model.cases:
        for step in case.steps:
            if step.selector is None:
                continue
            key = target_key(step.selector)
            if key not in seen:
                seen[key] = step.selector
                order.append(key)
    return [(k, seen[k]) for k in order]


def _param_name(target: str, used: set) -> str:
    """A clean Examples-column name for a form field (e.g. Email -> email)."""
    base = re.sub(r"[^0-9a-zA-Z_]", "_", snake(target)).strip("_") or "value"
    name, i = base, 2
    while name in used:
        name, i = f"{base}{i}", i + 1
    used.add(name)
    return name


def _variant(param: str, value: str) -> str:
    """A second, illustrative Examples row so the table reads as a template."""
    p = param.lower()
    if "email" in p:
        return "user2@example.com"
    if "pass" in p or "pwd" in p or "secure" in p:
        return "Secret123!"
    if "phone" in p or "tel" in p:
        return "0987654321"
    return f"{value} 2".strip()


def _type_outline(case) -> Optional[List[str]]:
    """If the case fills a form, render it as a Scenario Outline whose typed
    values are Examples columns — the tester plugs their own data in the table."""
    type_steps = [s for s in case.steps if s.action is ActionType.TYPE and s.selector is not None]
    if not type_steps:
        return None
    used: set = set()
    params = {id(s): _param_name(target_key(s.selector), used) for s in type_steps}
    lines = [f"  Scenario Outline: {case.description or case.name}"]
    prev = None
    for step in case.steps:
        clause = _CLAUSE[step.action]
        keyword = "And" if clause == prev else clause
        lines.append(f"    {keyword} {phrase(step, params.get(id(step)))}")
        prev = clause
    names = [params[id(s)] for s in type_steps]
    lines.append("")
    lines.append("    Examples:")
    lines.append("      | " + " | ".join(names) + " |")
    lines.append("      | " + " | ".join((s.text or "").strip() for s in type_steps) + " |")
    lines.append("      | " + " | ".join(_variant(params[id(s)], (s.text or "").strip()) for s in type_steps) + " |")
    return lines


def _visible_outline(case) -> Optional[List[str]]:
    """If the case only asserts visibility of many elements, collapse it to one
    Scenario Outline over "<element>" is visible with an Examples table."""
    targets: List[str] = []
    seen: set = set()
    for step in case.steps:
        if step.action is ActionType.LAUNCH:
            continue
        if step.action is not ActionType.ASSERT or step.selector is None:
            return None  # has taps/types -> not a plain state case
        if step.assertion is AssertionType.VISIBLE:
            key = target_key(step.selector)
            if key not in seen:
                seen.add(key)
                targets.append(key)
        # ENABLED asserts are folded away — visibility already covers presence.
    if len(targets) < 2:
        return None
    lines = [
        f"  Scenario Outline: {case.description or case.name}",
        "    Given the app is launched",
        '    Then "<element>" is visible',
        "",
        "    Examples:",
        "      | element |",
    ]
    lines += [f"      | {t} |" for t in targets]
    return lines


def render_feature(model: TestModel) -> str:
    """Render the language-agnostic Gherkin feature file. Cases that fill forms or
    assert many elements become parameterized Scenario Outlines (Examples tables);
    the rest stay plain Scenarios. Identical bytes across step-def languages."""
    out: List[str] = [f"Feature: {model.name}"]
    if model.description:
        out.append(f"  {model.description}")
    out.append("")
    for case in model.cases:
        block = _type_outline(case) or _visible_outline(case)
        if block is None:
            block = [f"  Scenario: {case.description or case.name}"]
            for line in scenario_lines(case.steps):
                block.append(f"    {line['keyword']} {line['phrase']}")
        out.extend(block)
        out.append("")
    return "\n".join(out) + "\n"
