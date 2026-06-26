"""
Codegen IR — language-agnostic Intermediate Representation for generated tests.

This is the single source of truth for *what* a test does. It carries no
language- or framework-specific syntax. Emitters (one per target language)
turn an :class:`TestModel` into runnable source code via templates.

Pipeline:  FlowGraph/Screens -> ir_builder -> TestModel -> Emitter -> files

Everything here is plain dataclasses with ``to_dict``/``from_dict`` so IR can
be serialized as JSON fixtures for golden-file tests (no device required).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ActionType(Enum):
    """A single interaction the test performs."""
    LAUNCH = "launch"        # start the app under test
    TAP = "tap"              # tap an element
    TYPE = "type"            # type text into an element
    SWIPE = "swipe"          # swipe in a direction
    WAIT = "wait"            # wait for an element / timeout
    BACK = "back"            # press the system back button
    ASSERT = "assert"        # verify an expectation


class AssertionType(Enum):
    """The expectation checked by an ``ASSERT`` action."""
    VISIBLE = "visible"
    NOT_VISIBLE = "not_visible"
    ENABLED = "enabled"
    TEXT_EQUALS = "text_equals"


class SelectorStrategy(Enum):
    """Abstract locator strategy. Each emitter maps these to its own binding
    (e.g. AppiumBy.ID for Python, By.id(...) for Java). Keeping the strategy
    abstract is what keeps the IR language-agnostic."""
    ID = "id"
    ACCESSIBILITY_ID = "accessibility_id"
    XPATH = "xpath"
    CLASS_NAME = "class_name"
    TEXT = "text"


@dataclass
class Selector:
    """How to locate an element, with ranked fallbacks for self-healing.

    ``score`` is the stability score (0..1) from selector_scorer; emitters may
    surface it as a comment so a human can see how fragile a locator is.
    """
    strategy: SelectorStrategy
    value: str
    score: float = 1.0
    description: str = ""
    fallbacks: List["Selector"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "value": self.value,
            "score": self.score,
            "description": self.description,
            "fallbacks": [f.to_dict() for f in self.fallbacks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Selector":
        return cls(
            strategy=SelectorStrategy(data["strategy"]),
            value=data["value"],
            score=data.get("score", 1.0),
            description=data.get("description", ""),
            fallbacks=[cls.from_dict(f) for f in data.get("fallbacks", [])],
        )


@dataclass
class Step:
    """One step of a test case."""
    action: ActionType
    selector: Optional[Selector] = None
    text: Optional[str] = None                  # for TYPE
    assertion: Optional[AssertionType] = None   # for ASSERT
    expected: Optional[str] = None              # for ASSERT TEXT_EQUALS
    direction: Optional[str] = None             # for SWIPE: up/down/left/right
    timeout: Optional[float] = None             # for WAIT
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"action": self.action.value}
        if self.selector is not None:
            out["selector"] = self.selector.to_dict()
        if self.text is not None:
            out["text"] = self.text
        if self.assertion is not None:
            out["assertion"] = self.assertion.value
        if self.expected is not None:
            out["expected"] = self.expected
        if self.direction is not None:
            out["direction"] = self.direction
        if self.timeout is not None:
            out["timeout"] = self.timeout
        if self.description:
            out["description"] = self.description
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Step":
        return cls(
            action=ActionType(data["action"]),
            selector=Selector.from_dict(data["selector"]) if data.get("selector") else None,
            text=data.get("text"),
            assertion=AssertionType(data["assertion"]) if data.get("assertion") else None,
            expected=data.get("expected"),
            direction=data.get("direction"),
            timeout=data.get("timeout"),
            description=data.get("description", ""),
        )


@dataclass
class TestCase:
    """A named sequence of steps — typically one path through the app flow."""
    __test__ = False  # not a pytest test class despite the name
    name: str
    steps: List[Step] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            steps=[Step.from_dict(s) for s in data.get("steps", [])],
        )


class Platform(Enum):
    ANDROID = "android"
    IOS = "ios"


@dataclass
class TestModel:
    """A full generated test suite, ready to hand to any emitter."""
    __test__ = False  # not a pytest test class despite the name
    name: str                                 # suite / class name, e.g. "LoginFlow"
    app_package: str                            # app under test, e.g. "com.example.app"
    platform: Platform = Platform.ANDROID
    cases: List[TestCase] = field(default_factory=list)
    app_activity: Optional[str] = None          # Android entry activity
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "app_package": self.app_package,
            "platform": self.platform.value,
            "app_activity": self.app_activity,
            "description": self.description,
            "cases": [c.to_dict() for c in self.cases],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestModel":
        return cls(
            name=data["name"],
            app_package=data["app_package"],
            platform=Platform(data.get("platform", "android")),
            app_activity=data.get("app_activity"),
            description=data.get("description", ""),
            cases=[TestCase.from_dict(c) for c in data.get("cases", [])],
        )
