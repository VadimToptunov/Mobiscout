"""
Codegen IR — language-agnostic Intermediate Representation for generated tests.

This is the single source of truth for *what* a test does. It carries no
language- or framework-specific syntax. Emitters (one per target language)
turn an :class:`TestModel` into runnable source code via templates.

Pipeline:  AppModel / CrawlResult -> (app_model_adapter | crawler.to_codegen) -> TestModel -> Emitter -> files

Everything here is plain dataclasses with ``to_dict``/``from_dict`` so IR can
be serialized as JSON fixtures for golden-file tests (no device required).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from framework.domain import Platform


class ActionType(Enum):
    """A single interaction the test performs."""

    LAUNCH = "launch"  # start the app under test
    TAP = "tap"  # tap an element
    TYPE = "type"  # type text into an element
    SWIPE = "swipe"  # swipe in a direction
    WAIT = "wait"  # wait for an element / timeout
    BACK = "back"  # press the system back button
    ASSERT = "assert"  # verify an expectation
    LONG_PRESS = "long_press"  # long-press an element
    SCROLL_TO = "scroll_to"  # scroll until an element is on screen
    DEEP_LINK = "deep_link"  # open a deep link / URL scheme (step.text = url)
    PRESS_KEY = "press_key"  # press a hardware/soft key (step.text = key name)
    SWITCH_CONTEXT = "switch_context"  # switch native<->webview context (step.text = "web" | "native")


class AssertionType(Enum):
    """The expectation checked by an ``ASSERT`` action."""

    VISIBLE = "visible"
    NOT_VISIBLE = "not_visible"
    ENABLED = "enabled"
    TEXT_EQUALS = "text_equals"
    # The app under test is still running in the foreground (it did not crash). Carries no
    # selector; only the Page-Object framework kits render it (defect tests).
    APP_RUNNING = "app_running"


class SelectorStrategy(Enum):
    """Abstract locator strategy. Each emitter maps these to its own binding
    (e.g. AppiumBy.ID for Python, By.id(...) for Java). Keeping the strategy
    abstract is what keeps the IR language-agnostic.

    The ``FLUTTER_*`` strategies are the widget-tree finders of the
    appium-flutter-integration-driver (Route B): a Flutter app paints into one
    opaque canvas, so the only locators that resolve at runtime are the driver's
    own finders (W3C strategies ``-flutter key`` / ``-flutter semantics label`` /
    ``-flutter text`` / ``-flutter type``). They are a closed family — a Flutter
    selector never falls back to a native strategy, which would not resolve on
    the canvas — and only the Appium Python/Java/Kotlin kits bind them."""

    ID = "id"
    ACCESSIBILITY_ID = "accessibility_id"
    XPATH = "xpath"
    CLASS_NAME = "class_name"
    TEXT = "text"
    FLUTTER_KEY = "flutter_key"  # ValueKey — developer-assigned, most stable
    FLUTTER_SEMANTICS = "flutter_semantics"  # Semantics label (accessibility)
    FLUTTER_TEXT = "flutter_text"  # visible widget text
    FLUTTER_TYPE = "flutter_type"  # widget type — last resort (first of type)


# The finders only the appium-flutter-integration-driver understands. A kit that
# cannot emit them (a native kit like Espresso, or one with no published Flutter
# binding like WebdriverIO/.NET) must fail loudly rather than emit a native
# locator that would never resolve on the Flutter canvas.
FLUTTER_STRATEGIES = frozenset(
    {
        SelectorStrategy.FLUTTER_KEY,
        SelectorStrategy.FLUTTER_SEMANTICS,
        SelectorStrategy.FLUTTER_TEXT,
        SelectorStrategy.FLUTTER_TYPE,
    }
)


def unsupported_flutter(kit: str) -> ValueError:
    """A clear error for a kit asked to render a Flutter (Route B) locator it has
    no published finder for — see :data:`FLUTTER_STRATEGIES`."""
    return ValueError(
        f"{kit} cannot locate Flutter widgets (Route B): the "
        f"appium-flutter-integration-driver needs its own key/semantics/text/type "
        f"finders. Generate the Appium Python, Java, or Kotlin kit for a Flutter app."
    )


@dataclass
class Selector:
    """How to locate an element, with ranked fallbacks for self-healing.

    ``score`` is a stability estimate (0..1, higher = more stable): the strategy
    tier (accessibility-id > resource-id > text) with a penalty for dynamic text.
    The model path ranks candidates by it; emitters may surface it as a comment so
    a human can see how fragile a locator is.
    """

    strategy: SelectorStrategy
    value: str
    score: float = 1.0
    description: str = ""
    fallbacks: List["Selector"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict (enum → value; fallbacks recursed)."""
        return {
            "strategy": self.strategy.value,
            "value": self.value,
            "score": self.score,
            "description": self.description,
            "fallbacks": [f.to_dict() for f in self.fallbacks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Selector":
        """Rebuild a Selector (and its fallback chain) from :meth:`to_dict` output."""
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
    text: Optional[str] = None  # for TYPE
    assertion: Optional[AssertionType] = None  # for ASSERT
    expected: Optional[str] = None  # for ASSERT TEXT_EQUALS
    direction: Optional[str] = None  # for SWIPE: up/down/left/right
    timeout: Optional[float] = None  # for WAIT
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a compact dict, omitting the fields this action doesn't use."""
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
        """Rebuild a Step from :meth:`to_dict` output, restoring enums and nested selector."""
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


@dataclass
class TestModel:
    """A full generated test suite, ready to hand to any emitter."""

    __test__ = False  # not a pytest test class despite the name
    name: str  # suite / class name, e.g. "LoginFlow"
    app_package: str  # app under test, e.g. "com.example.app"
    platform: Platform = Platform.ANDROID
    cases: List[TestCase] = field(default_factory=list)
    app_activity: Optional[str] = None  # Android entry activity
    description: str = ""
    # UI toolkit of the app under test: native | compose | flutter | hybrid. It
    # changes how elements must be located, so emitters surface the right guidance.
    toolkit: str = "native"
    # App launch arguments used during the crawl (e.g. skip a login gate). Emitted
    # into the driver setup so generated tests start in the same state the crawl did.
    launch_args: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "app_package": self.app_package,
            "platform": self.platform.value,
            "app_activity": self.app_activity,
            "description": self.description,
            "toolkit": self.toolkit,
            "launch_args": list(self.launch_args),
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
            toolkit=data.get("toolkit", "native"),
            launch_args=list(data.get("launch_args", [])),
            cases=[TestCase.from_dict(c) for c in data.get("cases", [])],
        )


def uses_flutter_finders(model: TestModel) -> bool:
    """Whether a model locates with Flutter integration-driver finders (Route B) rather
    than native locators (Route A).

    A ``toolkit == "flutter"`` model can be either: **Route B** (a cooperating build +
    the integration driver) carries ``FLUTTER_*`` selectors — real widget finders — while
    **Route A** (a foreign app with no integration driver) carries the native
    semantics/text locators the app projects into the accessibility tree. The two need
    different guidance, so the emitters tell them apart by the selector strategies the
    model actually uses, not by ``toolkit`` alone.
    """

    def _is_flutter(sel: Selector) -> bool:
        return sel.strategy in FLUTTER_STRATEGIES or any(_is_flutter(f) for f in sel.fallbacks)

    return any(step.selector is not None and _is_flutter(step.selector) for case in model.cases for step in case.steps)
