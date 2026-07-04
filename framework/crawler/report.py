"""
Crawl artifacts — the tester-facing outputs of a crawl.

Beyond generated tests, a crawl yields a reusable "test kit": a per-screen
element inventory (with the recommended locator for each element), a flow map of
the discovered navigation, and an accessibility report. These are exported as
Markdown (for docs/READMEs) and JSON (for tooling), so a tester can write auto
tests in any language just by reading them.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import _selector_for, audit_accessibility


def _locator(element: CrawlElement) -> Dict[str, str]:
    sel = _selector_for(element)
    if sel is None:
        return {"strategy": "", "value": ""}
    return {"strategy": sel.strategy.value, "value": sel.value}


def _owned(screen: CrawlScreen, app_package: str) -> List[CrawlElement]:
    return [e for e in screen.elements if not app_package or e.package in ("", app_package)]


def inventory_json(result: CrawlResult, app_package: str = "") -> Dict[str, Any]:
    """Machine-readable screen/element inventory + flow map."""
    fps = list(result.screens)
    screens = []
    for index, (fp, screen) in enumerate(result.screens.items(), 1):
        elements = []
        for e in _owned(screen, app_package):
            elements.append(
                {
                    "class": e.class_name,
                    "resource_id": e.resource_id,
                    "text": e.text,
                    "content_desc": e.content_desc,
                    "clickable": e.clickable,
                    "bounds": list(e.bounds),
                    "locator": _locator(e),
                }
            )
        screens.append(
            {
                "index": index,
                "platform": screen.platform,
                "toolkit": screen.toolkit,
                "fingerprint": fp,
                "element_count": len(elements),
                "elements": elements,
            }
        )
    flows = [
        {"from": fps.index(f) + 1, "tap": el.label or el.class_name, "to": fps.index(t) + 1}
        for f, el, t in result.transitions
        if f in fps and t in fps
    ]
    return {"app_package": app_package, "screen_count": len(screens), "screens": screens, "flows": flows}


def inventory_markdown(result: CrawlResult, app_package: str = "") -> str:
    """Human-readable element inventory (per screen) + flow map + a11y summary."""
    data = inventory_json(result, app_package)
    out: List[str] = [f"# Screen inventory — `{app_package or 'app'}`", ""]
    out.append(f"{data['screen_count']} screen(s) discovered by autonomous crawl.\n")

    for screen in data["screens"]:
        out.append(f"## Screen {screen['index']} · {screen['toolkit']} · {screen['platform']}")
        out.append(f"_{screen['element_count']} element(s) · fingerprint `{screen['fingerprint'][:12]}`_\n")
        out.append("| Element | Locator | Interactive |")
        out.append("|---|---|---|")
        for e in screen["elements"]:
            label = e["text"] or e["content_desc"] or e["resource_id"] or e["class"]
            loc = f"`{e['locator']['strategy']}={e['locator']['value']}`" if e["locator"]["value"] else "—"
            out.append(f"| {label[:40]} | {loc} | {'✓' if e['clickable'] else ''} |")
        out.append("")

    if data["flows"]:
        out.append("## Discovered flows")
        out.append("| From | Tap | To |")
        out.append("|---|---|---|")
        for f in data["flows"]:
            out.append(f"| Screen {f['from']} | {f['tap'][:30]} | Screen {f['to']} |")
        out.append("")

    findings = audit_accessibility(result, app_package)
    out.append("## Accessibility")
    if findings:
        out.append(f"{len(findings)} clickable element(s) without an accessible label:\n")
        for f in findings:
            out.append(f"- Screen {f.screen_index}: `{f.class_name}` at {f.bounds}")
    else:
        out.append("No accessibility issues found (all interactive elements are labelled).")
    out.append("")
    return "\n".join(out)


def inventory_json_str(result: CrawlResult, app_package: str = "") -> str:
    return json.dumps(inventory_json(result, app_package), indent=2)
