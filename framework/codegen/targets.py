"""
Target registry — a generation target is a (language, runner, binding) triple,
NOT just a language. Java can be TestNG or JUnit; JS can be WebdriverIO or a
bare Appium client. The registry maps a target id to its emitter.

Emitters register themselves here so adding a language is a single new module
plus a template folder — the core never changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from framework.core.engine import Language


@dataclass(frozen=True)
class Target:
    """An emission target."""
    id: str                 # stable key, e.g. "python_pytest"
    language: Language
    runner: str             # e.g. "pytest", "testng", "webdriverio"
    binding: str            # client library, e.g. "appium"
    file_extension: str     # ".py", ".java", ...
    description: str = ""


# Emitter factory signature: () -> Emitter instance
EmitterFactory = Callable[[], "object"]

_REGISTRY: Dict[str, "tuple[Target, EmitterFactory]"] = {}


def register(target: Target, factory: EmitterFactory) -> None:
    """Register an emitter factory for a target id."""
    if target.id in _REGISTRY:
        raise ValueError(f"Target already registered: {target.id}")
    _REGISTRY[target.id] = (target, factory)


def get_target(target_id: str) -> Target:
    if target_id not in _REGISTRY:
        raise KeyError(
            f"Unknown target '{target_id}'. Available: {', '.join(sorted(_REGISTRY))}"
        )
    return _REGISTRY[target_id][0]


def get_emitter(target_id: str):
    """Instantiate the emitter registered for ``target_id``."""
    if target_id not in _REGISTRY:
        raise KeyError(
            f"Unknown target '{target_id}'. Available: {', '.join(sorted(_REGISTRY))}"
        )
    return _REGISTRY[target_id][1]()


def available_targets() -> List[Target]:
    return [t for t, _ in _REGISTRY.values()]
