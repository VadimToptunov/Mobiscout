"""Bridge static source analysis into an ``AppModel`` for UI-test codegen.

The Android analyzer (``AndroidAnalyzer``) discovers screens, UI elements and
navigation from Kotlin/Compose source into an ``AnalysisResult``, but nothing
turned that into the ``AppModel`` the codegen pipeline consumes — so "explore the
source, build the element trees, write Appium UI tests" dead-ended at a JSON
report. This adapter closes that gap: ``AnalysisResult`` → ``AppModel`` →
``build_smoke_model`` → the emitters, so ``generate tests --source`` produces
runnable UI tests from the app's own code.

Locators are derived from what the source exposes, best-first: a Compose
``contentDescription`` (accessibility id), else a ``testTag`` / view id
(resource-id), else the visible text.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from framework.model.app_model import AppModel, AppModelMeta
from framework.model.element import Element
from framework.model.enums import ElementType, Platform
from framework.model.screen import Screen
from framework.model.selector import Selector

# UIElementCandidate.type (source term) -> AppModel ElementType.
_ELEMENT_TYPE = {
    "button": ElementType.BUTTON,
    "textfield": ElementType.INPUT,
    "textinput": ElementType.INPUT,
    "input": ElementType.INPUT,
    "edittext": ElementType.INPUT,
    "outlinedtextfield": ElementType.INPUT,
    "text": ElementType.TEXT,
    "image": ElementType.IMAGE,
    "icon": ElementType.IMAGE,
    "checkbox": ElementType.CHECKBOX,
    "switch": ElementType.SWITCH,
    "lazycolumn": ElementType.LIST,
    "lazyrow": ElementType.LIST,
    "list": ElementType.LIST,
}


def _element_type(raw: Optional[str]) -> ElementType:
    return _ELEMENT_TYPE.get((raw or "").strip().lower(), ElementType.GENERIC)


def _element_selector(candidate: Any) -> Optional[Selector]:
    """The most reliable *runtime* locator the source exposes for an element, or
    None. Uses only things a device can actually match — a Compose
    ``contentDescription``, a ``testTag`` (resource-id), or visible text — not the
    analyzer's synthesized ``id`` (a code identifier, not a device locator)."""
    content_desc = getattr(candidate, "content_description", None)
    if content_desc:
        return Selector(test_id=content_desc)  # -> ACCESSIBILITY_ID
    test_tag = getattr(candidate, "test_tag", None)
    if test_tag:
        return Selector(android=f"id:{test_tag}")  # testTagsAsResourceId -> resource-id
    text = getattr(candidate, "text", None)
    if text:
        return Selector(android=f"text:{text}")
    return None


def analysis_to_app_model(result: Any, app_version: str = "1.0.0", platform: Platform = Platform.ANDROID) -> AppModel:
    """Map an ``AnalysisResult`` (screens + ui_elements) to an ``AppModel``.

    Elements are grouped by their screen; those with no derivable locator are
    dropped (a UI test can't assert on them). Screens are taken from both the
    discovered screen list and any screen an element references. ``platform`` is
    stamped on the model so codegen emits the right driver/locators (the accessory
    locators — accessibility id, text — work on both; it drives the setup)."""
    by_screen: Dict[str, List[Any]] = defaultdict(list)
    for candidate in getattr(result, "ui_elements", []) or []:
        by_screen[getattr(candidate, "screen", None) or "app"].append(candidate)

    screen_names = {getattr(s, "name", "") for s in getattr(result, "screens", []) or []} | set(by_screen)
    screen_names.discard("")

    screens: Dict[str, Screen] = {}
    for name in sorted(screen_names):
        elements: List[Element] = []
        for index, candidate in enumerate(by_screen.get(name, [])):
            selector = _element_selector(candidate)
            if selector is None:
                continue
            elements.append(
                # Optional model fields default via pydantic Field(); mypy can't see
                # that without the plugin (as elsewhere in the codebase).
                Element(  # type: ignore[call-arg]
                    id=getattr(candidate, "id", "") or f"{name}_el_{index}",
                    type=_element_type(getattr(candidate, "type", None)),
                    selector=selector,
                    text=getattr(candidate, "text", None),
                )
            )
        screens[name] = Screen(name=name, elements=elements)  # type: ignore[call-arg]

    return AppModel(meta=AppModelMeta(app_version=app_version, platform=platform), screens=screens)


def source_app_model(source_path: str) -> AppModel:
    """Statically analyze an app source tree into an ``AppModel`` ready for
    ``build_smoke_model`` — the source → UI-tests entry point. Auto-detects the
    platform: Swift (iOS/SwiftUI) else Kotlin/Java (Android/Compose)."""
    return source_smoke_inputs(source_path)[0]


def source_smoke_inputs(source_path: str) -> Tuple[AppModel, NavigationPaths]:
    """The ``AppModel`` and the per-screen navigation paths (see :func:`navigation_paths`)
    for an app source tree — everything ``build_smoke_model`` needs to write cases that reach
    each screen before checking it."""
    from framework.crawler.source_graph import analyze_source_tree

    result = analyze_source_tree(source_path)
    platform = Platform.IOS if result.platform == "ios" else Platform.ANDROID
    return analysis_to_app_model(result, platform=platform), navigation_paths(result)


@dataclass
class NavigationPaths:
    """How each screen is reached from the one the app opens on."""

    entry: Optional[str]  # the screen the app opens on, when the source says
    taps: Dict[str, List[Element]] = field(default_factory=dict)  # screen -> controls to tap, in order


def _trigger_element(nav: Any, platform: str, index: int) -> Optional[Element]:
    """The control a navigation edge is tapped through, as a locatable element — its testTag /
    accessibilityIdentifier, else its visible text — or None when the source doesn't say."""
    if nav.trigger_test_tag:
        selector = (
            Selector(test_id=nav.trigger_test_tag)
            if platform == "ios"
            else Selector(android=f"id:{nav.trigger_test_tag}")
        )
    elif nav.trigger:
        # iOS matches a control's label as its accessibility id; Android by its text.
        selector = Selector(test_id=nav.trigger) if platform == "ios" else Selector(android=f"text:{nav.trigger}")
    else:
        return None
    return Element(  # type: ignore[call-arg]
        id=nav.trigger_test_tag or nav.trigger or f"nav_{index}",
        type=ElementType.BUTTON,
        selector=selector,
        text=nav.trigger,
    )


def navigation_paths(result: Any) -> NavigationPaths:
    """Per screen, the shortest run of taps from the entry screen that reaches it, over the
    navigation edges whose triggering control the source names. A screen no such path
    reaches is absent (its case keeps launch-only, saying why)."""
    from framework.crawler.source_graph import destination_resolver

    resolve = destination_resolver(result)
    entry = resolve(result.entry_screen) if getattr(result, "entry_screen", None) else None
    paths = NavigationPaths(entry=entry)
    if entry is None:
        return paths
    edges: Dict[str, List[Tuple[str, Element]]] = defaultdict(list)
    for index, nav in enumerate(result.navigation):
        if not nav.from_screen:
            continue  # a route registry entry, not a call site
        trigger = _trigger_element(nav, result.platform or "android", index)
        if trigger is not None:
            edges[nav.from_screen].append((resolve(nav.to_screen), trigger))
    paths.taps[entry] = []
    queue = deque([entry])
    while queue:
        here = queue.popleft()
        for there, trigger in edges.get(here, []):
            if there not in paths.taps:
                paths.taps[there] = [*paths.taps[here], trigger]
                queue.append(there)
    return paths
