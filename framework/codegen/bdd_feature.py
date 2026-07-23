"""
BDD feature-file generation via the codegen pipeline.

Builds Gherkin .feature files from the canonical AppModel's flows. Supersedes
generators/bdd_gen.py (whose template referenced a non-existent ``flow.scenarios``
field; this reads the real ``flow.steps``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.model.app_model import AppModel, Flow

import re
from typing import Dict


def _slug(name: str) -> str:
    """A clean feature-file slug: lowercase, non-alphanumerics collapsed to '_'."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_") or "flow"


def _step_phrase(step: dict) -> str:
    """Render one flow step (a screen/action mapping) as Gherkin step text."""
    action = step.get("action")
    screen = step.get("screen")
    if action and screen:
        return f'{action} on "{screen}"'
    if action:
        return str(action)
    return " ".join(str(v) for v in step.values()) or "continue"


def _render_feature(flow: Flow) -> str:
    lines = [f"Feature: {flow.name}"]
    if flow.description:
        lines.append(f"  {flow.description}")
    lines.append("")
    lines.append(f"  Scenario: {flow.name}")
    for i, step in enumerate(flow.steps):
        keyword = "When" if i == 0 else "And"
        lines.append(f"    {keyword} {_step_phrase(step)}")
    if not flow.steps:
        lines.append("    When the flow runs")
    lines.append("")
    return "\n".join(lines) + "\n"


def emit_feature_files(app_model: AppModel) -> Dict[str, str]:
    """Render one .feature file per flow. Returns ``{filename: gherkin}``."""
    out: Dict[str, str] = {}
    for flow in app_model.flows:
        out[f"{_slug(flow.name)}.feature"] = _render_feature(flow)
    return out
