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

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    root = Path(source_path)
    if any(root.rglob("*.swift")) and not (any(root.rglob("*.kt")) or any(root.rglob("*.java"))):
        from framework.analyzers.ios_source_analyzer import IOSSourceAnalyzer

        return analysis_to_app_model(IOSSourceAnalyzer().analyze(source_path), platform=Platform.IOS)

    from framework.analyzers.android_analyzer import AndroidAnalyzer

    return analysis_to_app_model(AndroidAnalyzer().analyze(source_path), platform=Platform.ANDROID)
