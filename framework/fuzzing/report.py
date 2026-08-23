"""A shareable Markdown report for a fuzzing campaign.

Renders the campaign_results collected by FuzzingCampaign into a report a human can read
and share. It is scrupulously honest about *simulated* runs: when no real target was
exercised (UI fuzzing with no device driver), the inputs were generated but never sent, so
the report says so and reports **no findings** rather than implying crashes it never saw.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _section(title: str, results: Dict[str, Any]) -> List[str]:
    lines = [f"## {title}", ""]
    if not results:
        lines.append("_Not run._")
        lines.append("")
        return lines

    if results.get("simulated"):
        lines.append(
            "> ⚠️ **Simulated run** — no real target was exercised (no device/endpoint driver). "
            "Inputs were generated but not sent, so there are no findings to report. Attach a "
            "device/endpoint and re-run for real results."
        )
        lines.append("")

    total = results.get("total_inputs", results.get("total_requests", 0))
    problems = results.get("crashes", results.get("errors", 0))
    lines.append(f"- Inputs exercised: **{total}**")
    lines.append(f"- {'Crashes' if 'crashes' in results else 'Errors'}: **{problems}**")
    lines.append("")

    findings = results.get("findings") or []
    if findings and not results.get("simulated"):
        lines.append("### Findings")
        lines.append("")
        lines.append("| Target | Strategy | Input | Kind |")
        lines.append("|---|---|---|---|")
        for f in findings[:50]:
            where = f.get("target") or f.get("endpoint") or "?"
            kind = "crash" if f.get("crash") else "error"
            value = str(f.get("value", "")).replace("|", "\\|").replace("\n", " ")[:60]
            lines.append(f"| {where} | {f.get('strategy', '')} | `{value}` | {kind} |")
        lines.append("")
    elif not results.get("simulated"):
        lines.append("No crashes or errors observed. ✅")
        lines.append("")
    return lines


def fuzz_report(campaign_results: Dict[str, Any], title: str = "Fuzzing campaign report") -> str:
    """Render ``campaign_results`` (``{"ui": {...}, "api": {...}}``) to Markdown."""
    lines = [f"# {title}", ""]
    if not campaign_results:
        return "\n".join([*lines, "_No campaign has been run._", ""])
    if "ui" in campaign_results:
        lines += _section("UI fuzzing", campaign_results["ui"])
    if "api" in campaign_results:
        lines += _section("API fuzzing", campaign_results["api"])
    return "\n".join(lines)
