"""
Page Object generation via the codegen pipeline.

Produces Appium Page Object classes from the canonical pydantic AppModel,
reusing the same locator ranking + self-healing model as the test emitters.
This supersedes the legacy generators/page_object_gen.py.

    AppModel.Screen --(build_page_object)--> PageObject --(render)--> .py source
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.model.app_model import AppModel, Screen

import os
from dataclasses import dataclass, field
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from framework.codegen.app_model_adapter import _selector_for
from framework.codegen.emitters._naming import pascal, snake
from framework.codegen.emitters._python_common import locator_chain
from framework.codegen.ir import Selector

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "page_object")


@dataclass
class PageObjectField:
    """One element on the screen, exposed as a page-object accessor."""

    name: str  # snake_case accessor/field name
    selector: Selector  # ranked IR selector (primary + fallbacks)


@dataclass
class PageObject:
    """A page object for a single screen."""

    class_name: str
    screen_name: str
    fields: List[PageObjectField] = field(default_factory=list)


def build_page_object(screen: Screen) -> PageObject:
    """Build a PageObject from a pydantic model.Screen (locatable elements only)."""
    fields: List[PageObjectField] = []
    seen = set()
    for element in screen.elements:
        selector = _selector_for(element)
        if selector is None:
            continue
        name = snake(element.id)
        if name in seen:  # avoid duplicate accessors
            continue
        seen.add(name)
        fields.append(PageObjectField(name=name, selector=selector))
    return PageObject(class_name=f"{pascal(screen.name)}Page", screen_name=screen.name, fields=fields)


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    env.filters["locator_chain"] = locator_chain
    return env


def emit_page_objects(app_model: AppModel) -> Dict[str, str]:
    """Render one Appium Page Object module per screen with locatable elements.

    Returns a mapping of ``{filename: python_source}``.
    """
    template = _env().get_template("page_object.py.j2")
    out: Dict[str, str] = {}
    for screen in app_model.screens.values():
        po = build_page_object(screen)
        if not po.fields:
            continue
        out[f"{snake(po.class_name)}.py"] = template.render(po=po)
    return out
