"""
One suite for both platforms: merge an Android and an iOS Page-Object model of the same app.

Each platform is crawled on its own (a device each); the two models are then aligned the way a
person reads the app — by what the screens and controls are called:

* **pages** match by name (the screen title: "Welcome back" is the same screen on both);
* **elements** match by key (their label: "Email" is the same field) and carry a locator per
  platform — an element only one platform has keeps just its own;
* **scenarios** match by what they do (the same page calls): one both platforms produced runs on
  both; one only a platform produced (Back is Android-only) runs on that platform alone, and the
  other skips it saying why.

The merged model is an ordinary :class:`FrameworkModel` with its per-platform fields filled
(``apps``, ``ElementDef.selectors``, ``PageDef.identities``, ``Scenario.platforms``), so the BDD
layer and every renderer read it as before; a renderer that sees ``apps`` writes a kit that picks
the platform at run time (``MOBISCOUT_PLATFORM``).
"""

from __future__ import annotations

import copy
from typing import Dict, List, Tuple

from framework.codegen.framework_model import FrameworkModel, PageDef, PlatformApp, Scenario

PLATFORM_ENV = "MOBISCOUT_PLATFORM"


def _signature(sc: Scenario) -> tuple:
    return tuple((c.page, c.op, c.element, c.value) for c in sc.calls)


def _merge_page(into: PageDef, page: PageDef, platform: str) -> None:
    """Fold ``page`` (one platform's) into the merged ``into``."""
    by_key = {e.key: e for e in into.elements}
    for e in page.elements:
        mine = by_key.get(e.key)
        if mine is None:
            added = copy.deepcopy(e)
            added.selectors = {platform: e.selector}
            into.elements.append(added)
            by_key[e.key] = added
            continue
        mine.selectors[platform] = e.selector
        mine.navigates_to = mine.navigates_to or e.navigates_to
        if mine.role != "input" and e.role == "input":
            mine.role = "input"
    into.identities[platform] = page.identity
    into.queries |= page.queries


def merge_platform_models(models: Dict[str, FrameworkModel]) -> FrameworkModel:
    """Android + iOS models of one app -> one cross-platform model (see the module docs).

    ``models`` maps "android"/"ios" to that platform's model; the first is the primary (its
    pages come first and name the kit)."""
    platforms = list(models)
    first = models[platforms[0]]
    pages: Dict[str, PageDef] = {}
    for platform, fm in models.items():
        for page in fm.pages:
            if page.name not in pages:
                merged = copy.deepcopy(page)
                merged.elements, merged.identities, merged.queries = [], {}, set()
                pages[page.name] = merged
            _merge_page(pages[page.name], page, platform)
    for page in pages.values():
        # Each platform proves the page by its own identity element (``identities``);
        # ``identity`` just says the page can be proven — the BDD layer and the navigation
        # checks ask that. A scenario only runs where its checks were built, so a platform
        # without an identity never gets asked for one.
        page.identity = next((k for k in page.identities.values() if k), None)

    scenarios, skipped = _merge_scenarios(models, "scenarios"), _merge_scenarios(models, "skipped")
    return FrameworkModel(
        app_package=first.app_package,
        app_activity=first.app_activity,
        platform=first.platform,
        launch_args=list(first.launch_args),
        pages=list(pages.values()),
        scenarios=scenarios,
        skipped=skipped,
        apps={p: PlatformApp(fm.app_package, fm.app_activity, list(fm.launch_args)) for p, fm in models.items()},
    )


def _merge_scenarios(models: Dict[str, FrameworkModel], field: str) -> List[Scenario]:
    """Scenarios (or skipped ones) of every platform, one per behaviour, each saying where it
    runs; a name two different behaviours share gets the platform as a suffix."""
    by_sig: Dict[Tuple[str, tuple], Scenario] = {}
    order: List[Tuple[str, tuple]] = []
    for platform, fm in models.items():
        for sc in getattr(fm, field):
            key = (sc.name if sc.skip else "", _signature(sc))
            if key in by_sig:
                by_sig[key].platforms = [*(by_sig[key].platforms or []), platform]
                continue
            merged = copy.deepcopy(sc)
            merged.platforms = [platform]
            by_sig[key] = merged
            order.append(key)
    out = [by_sig[k] for k in order]
    everywhere = list(models)
    names: Dict[str, int] = {}
    for sc in out:
        names[sc.name] = names.get(sc.name, 0) + 1
    for sc in out:
        if sc.platforms == everywhere:
            sc.platforms = None  # runs on every platform — nothing to mark
        elif names[sc.name] > 1 and sc.platforms:
            sc.name = f"{sc.name}_{sc.platforms[0]}"
    return out
