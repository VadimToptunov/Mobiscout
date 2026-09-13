"""
Static interaction graph — build the app's screen/navigation graph from SOURCE,
before a single tap.

The dynamic crawler discovers screens by driving the live UI; this does the same
from source code, so a crawl can be *seeded with* — or *checked against* — a
predicted graph. It reuses the analyzers' :class:`AnalysisResult` (detected
screens + ``navigate()`` edges) and re-expresses it in the crawler's own
:class:`CrawlResult` shape, so :func:`build_graph` and every graph analysis /
Mermaid / DOT / JSON exporter work on it unchanged.

This is the source-first *seed*: today it produces the predicted graph with no
device; a later step will walk it on a device to confirm each node and edge (see
the source-first-crawl direction). Regex/heuristic like the analyzers it builds
on — a hypothesis of the app's structure, not a proof.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from framework.analyzers.analysis_result import AnalysisResult, UIElementCandidate
from framework.crawler.graph import InteractionGraph, build_graph
from framework.crawler.models import CrawlElement, CrawlResult, CrawlScreen, Transition

# A source UI type -> a platform class name, so classify() / selector_for() read a
# source element the way they read a live one. Unknown types fall back to a generic
# container (still a valid, if unclassified, node member).
_ANDROID_CLASS = {
    "button": "android.widget.Button",
    "textfield": "android.widget.EditText",
    "textinput": "android.widget.EditText",
    "text": "android.widget.TextView",
    "image": "android.widget.ImageView",
    "checkbox": "android.widget.CheckBox",
    "switch": "android.widget.Switch",
}
_IOS_CLASS = {
    "button": "XCUIElementTypeButton",
    "textfield": "XCUIElementTypeTextField",
    "textinput": "XCUIElementTypeTextField",
    "text": "XCUIElementTypeStaticText",
    "image": "XCUIElementTypeImage",
    "checkbox": "XCUIElementTypeSwitch",
    "switch": "XCUIElementTypeSwitch",
}
# The source types that a user acts on (so a synthetic element reads as clickable).
_ACTIONABLE = {"button", "textfield", "textinput", "checkbox", "switch"}


def _class_for(elem_type: Optional[str], platform: str) -> str:
    """Map a source element type to the platform class name the classifier expects."""
    key = (elem_type or "").strip().lower()
    table = _IOS_CLASS if platform == "ios" else _ANDROID_CLASS
    return table.get(key, "XCUIElementTypeOther" if platform == "ios" else "android.view.View")


def _normalize_route(route: str) -> str:
    """The stable part of a route: ``details/{id}`` and ``details/42`` both key on
    ``details``, so a ``navigate("details/42")`` call matches the screen that
    registered ``details/{id}``."""
    base = re.split(r"[/{?]", route or "", maxsplit=1)[0]
    return base.strip().strip("/").lower()


def _screen_key(name: str) -> str:
    """A screen name reduced to its route-like stem: ``DetailsScreen`` -> ``details``,
    so a ``navigate("details")`` with no sealed registry still connects to the screen
    named for it (the common Compose convention)."""
    return re.sub(r"(?:screen|page|view|fragment|activity)$", "", (name or "").lower())


def _element(candidate: UIElementCandidate, platform: str) -> CrawlElement:
    """A synthetic CrawlElement from a statically discovered UI element. Source has
    no geometry, so bounds are empty and locators come from the test tag / text /
    content-description the analyzer captured."""
    etype = (candidate.type or "").strip().lower()
    return CrawlElement(
        resource_id=candidate.test_tag or "",
        text=candidate.text or "",
        content_desc=candidate.content_description or "",
        class_name=_class_for(candidate.type, platform),
        clickable=etype in _ACTIONABLE,
        bounds=(0, 0, 0, 0),
        package="",
    )


def source_crawl_result(result: AnalysisResult) -> CrawlResult:
    """Translate a static :class:`AnalysisResult` into the crawler's
    :class:`CrawlResult` shape: one screen per detected screen (carrying its
    discovered elements), one transition per ``navigate()`` call (resolved from its
    route to the screen that registered it). The result flows through
    :func:`build_graph` exactly as a real crawl does."""
    platform = result.platform or "android"
    crawl = CrawlResult()

    # Elements grouped by the screen they were found in.
    by_screen: Dict[str, List[CrawlElement]] = {}
    for ui in result.ui_elements:
        if ui.screen:
            by_screen.setdefault(ui.screen, []).append(_element(ui, platform))

    def _add_screen(name: str, elements: Optional[List[CrawlElement]] = None) -> None:
        if name and name not in crawl.screens:
            crawl.screens[name] = CrawlScreen(fingerprint=name, elements=elements or [], platform=platform)

    # Route -> screen name. A screen's own route wins over a sealed-class registry
    # entry, so navigate() resolves to the composable node when both name it.
    route_to_screen: Dict[str, str] = {}
    name_stem_to_screen: Dict[str, str] = {}
    for screen in result.screens:
        _add_screen(screen.name, by_screen.get(screen.name, []))
        if screen.route:
            route_to_screen[_normalize_route(screen.route)] = screen.name
        name_stem_to_screen.setdefault(_screen_key(screen.name), screen.name)
    for nav in result.navigation:
        if nav.from_screen is None:  # a sealed-class route registry entry (route -> screen NAME)
            route_to_screen.setdefault(_normalize_route(nav.route), nav.to_screen)

    def _resolve(route: str) -> str:
        """A navigate() route -> its destination screen name: an explicit route
        registration first, else the screen whose name is that route (DetailsScreen
        for "details"), else the raw route as its own node."""
        key = _normalize_route(route)
        return route_to_screen.get(key) or name_stem_to_screen.get(key) or route

    # Edges: each navigate() call site (from_screen set) -> its resolved destination.
    for nav in result.navigation:
        if not nav.from_screen:
            continue  # a registry entry, not a call site
        dst = _resolve(nav.to_screen)
        _add_screen(nav.from_screen)  # a navigate() may sit in a non-"Screen" composable...
        _add_screen(dst)  # ...or point at a route with no detected screen
        element = CrawlElement(
            resource_id="",
            text=nav.trigger or nav.route,
            content_desc="",
            class_name=_class_for("button", platform),
            clickable=True,
            bounds=(0, 0, 0, 0),
            package="",
        )
        crawl.transitions.append(Transition(nav.from_screen, element, dst, kind="tap"))

    return crawl


def source_graph(result: AnalysisResult, app_package: str = "") -> InteractionGraph:
    """The static interaction graph for an analyzed app, ready for every
    :class:`InteractionGraph` analysis and exporter. Node names are the screen /
    composable names (the fingerprint the source pass assigns), so the graph reads."""
    graph = build_graph(source_crawl_result(result), app_package)
    for node in graph.nodes:
        node.name = node.fingerprint  # the source pass keys screens by their name
    return graph


def analyze_source_tree(source_path: str) -> AnalysisResult:
    """Run the platform-appropriate static analyzer over a source tree: Swift (with
    no Kotlin/Java) -> iOS/SwiftUI, else Android/Compose."""
    root = Path(source_path)
    if any(root.rglob("*.swift")) and not (any(root.rglob("*.kt")) or any(root.rglob("*.java"))):
        from framework.analyzers.ios_source_analyzer import IOSSourceAnalyzer

        return IOSSourceAnalyzer().analyze(source_path)

    from framework.analyzers.android_analyzer import AndroidAnalyzer

    return AndroidAnalyzer().analyze(source_path)
