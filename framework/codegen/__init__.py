"""
Language-agnostic code generation pipeline.

    Screens/FlowGraph --(ir_builder)--> TestModel --(emitter)--> source files

The IR (:mod:`framework.codegen.ir`) is the single source of truth; emitters
are thin, template-driven, and registered per target. This is the foundation
for supporting many test-automation languages without re-implementing the
generation logic per language.
"""

from framework.codegen.ir import (
    ActionType,
    AssertionType,
    Platform,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)
from framework.codegen.targets import (
    Target,
    available_targets,
    get_emitter,
    get_target,
    register,
)

# Importing emitter modules triggers their self-registration in the target
# registry. Add new languages here as they are implemented.
from framework.codegen.emitters import python_pytest  # noqa: F401,E402
from framework.codegen.emitters import python_pytest_bdd  # noqa: F401,E402

__all__ = [
    "ActionType",
    "AssertionType",
    "Platform",
    "Selector",
    "SelectorStrategy",
    "Step",
    "TestCase",
    "TestModel",
    "Target",
    "available_targets",
    "get_emitter",
    "get_target",
    "register",
]
