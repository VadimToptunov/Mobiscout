"""Service layer for ``mobiscout security comprehensive``.

Running the five security analyses (decompile, SAST, runtime, supply chain,
DAST), tallying severities, scoring runtime protections and saving the JSON
reports is plain logic that used to be tangled with the rich progress/table
rendering inside the command. It lives here so it can be unit-tested with stub
analyzers instead of real binaries.

The command in :mod:`framework.cli.security.comprehensive_cmd` stays a thin
shell: it renders the header/table/risk lines and turns :attr:`ComprehensiveScan.exit_code`
into the process exit status.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from framework.security.dast_analyzer import DASTAnalyzer
from framework.security.decompiler import Decompiler
from framework.security.runtime_protection import RuntimeProtectionAnalyzer
from framework.security.sast_analyzer import SASTAnalyzer
from framework.security.supply_chain import SupplyChainAnalyzer


@dataclass
class ComprehensiveScan:
    """The combined result of a comprehensive security scan.

    Attributes:
        decompile_result: Always-run binary decompilation result.
        sast_result: SAST result, or None if no source was available.
        runtime_result: Always-run runtime-protection analysis result.
        supply_result: Supply-chain result, or None if no source path.
        dast_result: DAST result, or None if no target host.
        total_critical: Critical findings summed across SAST/supply/DAST.
        total_high: High findings summed across SAST/supply/DAST.
        runtime_score: Percentage of runtime protections detected (0–100).
        analyses: ``(name, status, findings)`` rows for the summary table.
    """

    decompile_result: Any
    runtime_result: Any
    runtime_score: float
    sast_result: Optional[Any] = None
    supply_result: Optional[Any] = None
    dast_result: Optional[Any] = None
    total_critical: int = 0
    total_high: int = 0
    analyses: List[Tuple[str, str, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """Process exit status: 2 if any critical, 1 if any high, else 0."""
        if self.total_critical > 0:
            return 2
        if self.total_high > 0:
            return 1
        return 0


def _tally(items: Any, severity_of: Callable[[Any], str]) -> Tuple[int, int]:
    """Count critical/high severities in ``items``.

    Args:
        items: Iterable of findings/vulnerabilities.
        severity_of: Maps one item to its severity string.

    Returns:
        A ``(critical, high)`` count pair.
    """
    critical = high = 0
    for item in items:
        sev = severity_of(item)
        if sev == "critical":
            critical += 1
        elif sev == "high":
            high += 1
    return critical, high


def run_comprehensive_scan(
    app_path: Path,
    platform: str,
    *,
    source_path: Optional[Path] = None,
    target_host: Optional[str] = None,
    on_step: Optional[Callable[[str], None]] = None,
) -> ComprehensiveScan:
    """Run all five security analyses and assemble a :class:`ComprehensiveScan`.

    Decompilation and runtime-protection analysis always run; SAST runs against
    the given source (or the decompiled output), supply-chain runs only with a
    source path, and DAST runs only with a target host.

    Args:
        app_path: The app binary to analyze.
        platform: ``"android"`` or ``"ios"`` (selects runtime checks).
        source_path: Source tree for SAST/supply-chain (optional).
        target_host: Host for DAST (optional).
        on_step: Called with a human label before each of the five steps, for a
            progress display; ignored if None.

    Returns:
        The assembled scan result (sub-results, tallies, runtime score, table rows).
    """

    def step(label: str) -> None:
        if on_step:
            on_step(label)

    total_critical = 0
    total_high = 0
    sast_result = supply_result = dast_result = None

    # 1. Decompilation (always).
    step("[1/5] Decompiling binary...")
    decompile_result = Decompiler().decompile(app_path, extract_strings=True, analyze_native=True)

    # 2. SAST — against provided source, else the decompiled output.
    step("[2/5] Running SAST analysis...")
    sast_source = source_path or decompile_result.output_dir
    if sast_source and Path(sast_source).exists():
        sast_result = SASTAnalyzer().analyze(Path(sast_source))
        c, h = _tally(sast_result.findings, lambda f: f.severity.value)
        total_critical += c
        total_high += h

    # 3. Runtime protection (always).
    step("[3/5] Analyzing runtime protections...")
    runtime_result = RuntimeProtectionAnalyzer().analyze(app_path, platform)

    # 4. Supply chain — only with a source path.
    step("[4/5] Checking supply chain...")
    if source_path and source_path.exists():
        supply_result = SupplyChainAnalyzer().analyze(source_path)
        c, h = _tally(supply_result.vulnerabilities, lambda v: v.severity)
        total_critical += c
        total_high += h

    # 5. DAST — only with a target host.
    step("[5/5] Running DAST analysis...")
    if target_host:
        dast_result = DASTAnalyzer().analyze(target_host)
        c, h = _tally(dast_result.findings, lambda f: f.severity.value)
        total_critical += c
        total_high += h

    protections = [
        runtime_result.root_detection,
        runtime_result.emulator_detection,
        runtime_result.debug_detection,
        runtime_result.tamper_detection,
        runtime_result.hook_detection,
        runtime_result.ssl_pinning,
        runtime_result.obfuscation,
    ]
    detected = sum(1 for p in protections if p.detected)
    runtime_score = (detected / len(protections)) * 100

    analyses = [
        ("Binary Decompilation", "Complete", f"{len(decompile_result.security_findings)} issues"),
        (
            "SAST",
            "Complete" if sast_result else "Skipped",
            f"{len(sast_result.vulnerabilities) if sast_result else 0} vulnerabilities",
        ),
        ("Runtime Protection", "Complete", f"Score: {runtime_score:.0f}%"),
        (
            "Supply Chain",
            "Complete" if supply_result else "Skipped",
            f"{len(supply_result.vulnerabilities) if supply_result else 0} vulnerabilities",
        ),
        ("DAST", "Complete" if dast_result else "Skipped", f"{len(dast_result.findings) if dast_result else 0} issues"),
    ]

    return ComprehensiveScan(
        decompile_result=decompile_result,
        runtime_result=runtime_result,
        runtime_score=runtime_score,
        sast_result=sast_result,
        supply_result=supply_result,
        dast_result=dast_result,
        total_critical=total_critical,
        total_high=total_high,
        analyses=analyses,
    )


def save_reports(scan: ComprehensiveScan, output: Path, app_name: str, platform: str) -> None:
    """Write every analysis result plus a combined summary as JSON into ``output``.

    Only the analyses that actually ran are written; a combined
    ``{app_name}_summary.json`` records the tallies, runtime score and which
    analyses completed.

    Args:
        scan: The scan result to serialize.
        output: Destination directory (assumed to exist).
        app_name: Prefixes each report filename.
        platform: Recorded in the combined summary.
    """
    with open(output / f"{app_name}_decompile.json", "w") as f:
        json.dump(scan.decompile_result.to_dict(), f, indent=2, default=str)

    if scan.sast_result:
        with open(output / f"{app_name}_sast.json", "w") as f:
            json.dump(scan.sast_result.to_dict(), f, indent=2, default=str)

    with open(output / f"{app_name}_runtime.json", "w") as f:
        json.dump(scan.runtime_result.to_dict(), f, indent=2, default=str)

    if scan.supply_result:
        with open(output / f"{app_name}_supply_chain.json", "w") as f:
            json.dump(scan.supply_result.to_dict(), f, indent=2, default=str)

    if scan.dast_result:
        with open(output / f"{app_name}_dast.json", "w") as f:
            json.dump(scan.dast_result.to_dict(), f, indent=2, default=str)

    combined = {
        "app_name": app_name,
        "platform": platform,
        "total_critical": scan.total_critical,
        "total_high": scan.total_high,
        "runtime_score": scan.runtime_score,
        "analyses_completed": [a[0] for a in scan.analyses if a[1] == "Complete"],
    }
    with open(output / f"{app_name}_summary.json", "w") as f:
        json.dump(combined, f, indent=2)
