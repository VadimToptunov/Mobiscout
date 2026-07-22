"""
Comprehensive Security Analysis CLI Command

Command: comprehensive - runs all security analyses in one scan
"""

from pathlib import Path
from typing import Optional

import click
from rich.panel import Panel
from rich.table import Table

from framework.cli.security.comprehensive_service import run_comprehensive_scan, save_reports
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
        mobiscout security comprehensive app.apk -p android -n MyApp -o ./reports
        mobiscout security comprehensive app.apk -p android -n MyApp -s ./src -t api.example.com
    """
    if not validate_path(app_path):
        raise SystemExit(1)

    console.print(
        Panel.fit(
            "COMPREHENSIVE SECURITY ANALYSIS\n\n"
            f"App: {app_name}\n"
            f"Platform: {platform.upper()}\n"
            f"Binary: {app_path.name}\n"
            f"Source: {source_path or 'N/A'}\n"
            f"DAST Target: {target_host or 'N/A'}",
            style="bold red",
        )
    )

    if output:
        output.mkdir(parents=True, exist_ok=True)

    # Run the five analyses in the service, surfacing each step as a progress spinner.
    with create_progress_context() as progress:

        def _on_step(label: str) -> None:
            progress.add_task(label, total=None)

        scan = run_comprehensive_scan(
            app_path,
            platform,
            source_path=source_path,
            target_host=target_host,
            on_step=_on_step,
        )

    # Summary
    console.print()
    console.print(Panel.fit("COMPREHENSIVE ANALYSIS SUMMARY", style="bold green"))

    summary_table = Table()
    summary_table.add_column("Analysis", style="cyan")
    summary_table.add_column("Status", style="bold")
    summary_table.add_column("Findings")

    for name, status, findings in scan.analyses:
        status_style = "green" if status == "Complete" else "dim"
        summary_table.add_row(name, f"[{status_style}]{status}[/{status_style}]", findings)

    console.print(summary_table)

    # Risk assessment
    console.print(f"\n[bold]Total Critical Issues:[/bold] [red]{scan.total_critical}[/red]")
    console.print(f"[bold]Total High Issues:[/bold] [yellow]{scan.total_high}[/yellow]")

    if scan.total_critical > 0:
        console.print("\n[red bold]CRITICAL RISK - Immediate remediation required![/red bold]")
    elif scan.total_high > 5:
        console.print("\n[yellow bold]HIGH RISK - Significant security issues found[/yellow bold]")
    elif scan.runtime_score < 50:
        console.print("\n[yellow]MODERATE RISK - Missing runtime protections[/yellow]")
    else:
        console.print("\n[green]Application has reasonable security posture[/green]")

    # Save all reports
    if output:
        save_reports(scan, output, app_name, platform)
        console.print(f"\n[green]✓[/green] All reports saved to {output}/")

    raise SystemExit(scan.exit_code)
