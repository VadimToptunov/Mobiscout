"""
Emitter base — turns a language-agnostic :class:`TestModel` into source files.

Emitters are deliberately thin: all real syntax lives in Jinja2 templates under
``framework/codegen/templates/<target_id>/``. An emitter's job is to map the
abstract IR (selector strategies, action types) onto its language's binding and
feed the template. New language == new template folder + a thin subclass.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Dict

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from framework.codegen.ir import TestModel

_TEMPLATE_ROOT = os.path.join(os.path.dirname(__file__), "..", "templates")


class Emitter(ABC):
    """Base class for all language emitters."""

    #: target id, must match the template folder name under templates/
    target_id: str = ""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(os.path.join(_TEMPLATE_ROOT, self.target_id)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            undefined=StrictUndefined,  # fail loudly on a template typo, not silently
        )
        self._register_filters()

    def _register_filters(self) -> None:
        """Subclasses override to add language-specific Jinja filters."""

    @abstractmethod
    def emit(self, model: TestModel) -> Dict[str, str]:
        """Return a mapping of ``{relative_path: file_contents}``.

        A single suite may produce more than one file (e.g. page objects +
        test file); returning a dict keeps that open without changing callers.
        """
        raise NotImplementedError
