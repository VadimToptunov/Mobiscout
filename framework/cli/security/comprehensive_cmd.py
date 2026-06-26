"""
Comprehensive Security Analysis CLI Command

Command: comprehensive - runs all security analyses in one scan
"""

from pathlib import Path
from typing import Optional
import json

import click
from rich.panel import Panel
from rich.table import Table

from framework.security.sast_analyzer import SASTAnalyzer
from framework.security.dast_analyzer import DASTAnalyzer
from framework.security.decompiler import Decompiler
from framework.security.supply_chain import SupplyChainAnalyzer
from framework.security.runtime_protection import RuntimeProtectionAnalyzer
from framework.cli.security.base import (
    security,
    console,
    validate_path,
    create_progress_context,
)


@security.command(name="comprehensive")
@click.argument("app_path", type=Path)
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), required=True)
@click.option("--app-name", "-n", required=True, help="Application name")
@click.option("--source-path", "-s", type=Path, help="Source code path for SAST")
@click.option("--output", "-o", type=Path, help="Output directory for all reports")
@click.option("--target-host", "-t", type=str, help="Target host for DAST")
def comprehensive(
    app_path: Path,
    platform: str,
    app_name: str,
    source_path: Optional[Path],
    output: Optional[Path],
    target_host: Optional[str],
) -> None:
    """
    Run ALL security analyses in one comprehensive scan.

    Combines SAST, DAST, decompilation, supply chain, and runtime analysis.

    Example:
        observe security comprehensive app.apk -p android -n MyApp -o ./reports
        observe security comprehensive app.apk -p android -n MyApp -s ./src -t api.example.com
    """
    if not validate_path(app_path):
        raise SystemExit(1)

    console.print(Panel.fit(
        "COMPREHENSIVE SECURITY ANALYSIS\n\n"
        f"App: {app_name}\n"
        f"Platform: {platform.upper()}\n"
        f"Binary: {app_path.name}\n"
        f"Source: {source_path or 'N/A'}\n"
        f"DAST Target: {target_host or 'N/A'}",
        style="bold red"
    ))

    if output:
        output.mkdir(parents=True, exist_ok=True)

    total_critical = 0
    total_high = 0

    # Initialize optional results to None
    sast_result = None
    supply_result = None
    dast_result = None
    sast_source = None

    with create_progress_context() as progress:
        # 1. Decompilation
        task1 = progress.add_task("[1/5] Decompiling binary...", total=None)
        decompiler = Decompiler()
        decompile_result = decompiler.decompile(app_path, extract_strings=True, analyze_native=True)
        progress.update(task1, completed=True)

        # 2. SAST (if source provided or use decompiled)
        task2 = progress.add_task("[2/5] Running SAST analysis...", total=None)
        sast_analyzer = SASTAnalyzer()
        sast_source = source_path or decompile_result.output_dir
        if sast_source and Path(sast_source).exists():
            sast_result = sast_analyzer.analyze(Path(sast_source))
            for finding in sast_result.findings:
                if finding.severity.value == "critical":
                    total_critical += 1
                elif finding.severity.value == "high":
                    total_high += 1
        progress.update(task2, completed=True)

        # 3. Runtime Protection Analysis
        task3 = progress.add_task("[3/5] Analyzing runtime protections...", total=None)
        runtime_analyzer = RuntimeProtectionAnalyzer()
        runtime_result = runtime_analyzer.analyze(app_path, platform)
        progress.update(task3, completed=True)

        # 4. Supply Chain (if source provided)
        task4 = progress.add_task("[4/5] Checking supply chain...", total=None)
        if source_path and source_path.exists():
            supply_analyzer = SupplyChainAnalyzer()
            supply_result = supply_analyzer.analyze(source_path)
            for vuln in supply_result.vulnerabilities:
                if vuln.severity == "critical":
                    total_critical += 1
                elif vuln.severity == "high":
                    total_high += 1
        progress.update(task4, completed=True)

        # 5. DAST (if target provided)
        task5 = progress.add_task("[5/5] Running DAST analysis...", total=None)
        if target_host:
            dast_analyzer = DASTAnalyzer()
            dast_result = dast_analyzer.analyze(target_host)
            for finding in dast_result.findings:
                if finding.severity.value == "critical":
                    total_critical += 1
                elif finding.severity.value == "high":
                    total_high += 1
        progress.update(task5, completed=True)

    # Calculate runtime score from protection results
    protections = [
        runtime_result.root_detection,
        runtime_result.emulator_detection,
        runtime_result.debug_detection,
        runtime_result.tamper_detection,
        runtime_result.hook_detection,
        runtime_result.ssl_pinning,
        runtime_result.obfuscation,
    ]
    detected_count = sum(1 for p in protections if p.detected)
    runtime_score = (detected_count / len(protections)) * 100

    # Summary
    console.print()
    console.print(Panel.fit("COMPREHENSIVE ANALYSIS SUMMARY", style="bold green"))

    summary_table = Table()
    summary_table.add_column("Analysis", style="cyan")
    summary_table.add_column("Status", style="bold")
    summary_table.add_column("Findings")

    # Calculate findings counts safely
    sast_vuln_count = len(sast_result.vulnerabilities) if sast_result else 0
    supply_vuln_count = len(supply_result.vulnerabilities) if supply_result else 0
    dast_finding_count = len(dast_result.findings) if dast_result else 0

    analyses = [
        ("Binary Decompilation", "Complete", f"{len(decompile_result.security_findings)} issues"),
        ("SAST", "Complete" if sast_result else "Skipped", f"{sast_vuln_count} vulnerabilities"),
        ("Runtime Protection", "Complete", f"Score: {runtime_score:.0f}%"),
        ("Supply Chain", "Complete" if supply_result else "Skipped", f"{supply_vuln_count} vulnerabilities"),
        ("DAST", "Complete" if dast_result else "Skipped", f"{dast_finding_count} issues"),
    ]

    for name, status, findings in analyses:
        status_style = "green" if status == "Complete" else "dim"
        summary_table.add_row(name, f"[{status_style}]{status}[/{status_style}]", findings)

    console.print(summary_table)

    # Risk assessment
    console.print(f"\n[bold]Total Critical Issues:[/bold] [red]{total_critical}[/red]")
    console.print(f"[bold]Total High Issues:[/bold] [yellow]{total_high}[/yellow]")

    if total_critical > 0:
        console.print("\n[red bold]CRITICAL RISK - Immediate remediation required![/red bold]")
    elif total_high > 5:
        console.print("\n[yellow bold]HIGH RISK - Significant security issues found[/yellow bold]")
    elif runtime_score < 50:
        console.print("\n[yellow]MODERATE RISK - Missing runtime protections[/yellow]")
    else:
        console.print("\n[green]Application has reasonable security posture[/green]")

    # Save all reports
    if output:
        # Save individual reports
        with open(output / f"{app_name}_decompile.json", 'w') as f:
            json.dump(decompile_result.to_dict(), f, indent=2, default=str)

        if sast_result:
            with open(output / f"{app_name}_sast.json", 'w') as f:
                json.dump(sast_result.to_dict(), f, indent=2, default=str)

        with open(output / f"{app_name}_runtime.json", 'w') as f:
            json.dump(runtime_result.to_dict(), f, indent=2, default=str)

        if supply_result:
            with open(output / f"{app_name}_supply_chain.json", 'w') as f:
                json.dump(supply_result.to_dict(), f, indent=2, default=str)

        if dast_result:
            with open(output / f"{app_name}_dast.json", 'w') as f:
                json.dump(dast_result.to_dict(), f, indent=2, default=str)

        # Save combined summary
        combined = {
            "app_name": app_name,
            "platform": platform,
            "total_critical": total_critical,
            "total_high": total_high,
            "runtime_score": runtime_score,
            "analyses_completed": [a[0] for a in analyses if a[1] == "Complete"],
        }
        with open(output / f"{app_name}_summary.json", 'w') as f:
            json.dump(combined, f, indent=2)

        console.print(f"\n[green]✓[/green] All reports saved to {output}/")

    if total_critical > 0:
        raise SystemExit(2)
    elif total_high > 0:
        raise SystemExit(1)
    raise SystemExit(0)
