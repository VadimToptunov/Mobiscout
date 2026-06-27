"""
Supply Chain Security CLI Commands

Commands: supply-chain, sbom
"""

from pathlib import Path
from typing import Optional, Dict
import json

import click
from rich.panel import Panel
from rich.table import Table

from framework.security.supply_chain import SupplyChainAnalyzer
from framework.cli.security.base import (
    security,
    console,
    validate_path,
    create_progress_context,
)


@security.command(name="supply-chain")
@click.argument("project_path", type=Path)
@click.option("--output", "-o", type=Path, help="Output report path")
@click.option("--format", "-f", type=click.Choice(["json", "sbom", "html"]), default="json")
@click.option("--check-vulns/--no-vulns", default=True, help="Check for known vulnerabilities")
def supply_chain(
    project_path: Path,
    output: Optional[Path],
    format: str,
    check_vulns: bool,
) -> None:
    """
    Analyze supply chain security.

    Scans dependencies for vulnerabilities, generates SBOM, and checks licenses.

    Example:
        observe security supply-chain ./project
        observe security supply-chain ./app -o sbom.json --format sbom
        observe security supply-chain ./src --check-vulns
    """
    if not validate_path(project_path):
        raise SystemExit(1)

    console.print(
        Panel.fit(
            "Supply Chain Security Analysis\n\n"
            f"Project: {project_path}\n"
            f"Vulnerability Check: {'Enabled' if check_vulns else 'Disabled'}",
            style="bold blue",
        )
    )

    analyzer = SupplyChainAnalyzer()

    with create_progress_context() as progress:
        task = progress.add_task("Analyzing dependencies...", total=None)
        result = analyzer.analyze(project_path, check_vulnerabilities=check_vulns)
        progress.update(task, completed=True)

    console.print()
    console.print(Panel.fit("Supply Chain Analysis Results", style="bold green"))

    dep_table = Table(title=f"Dependencies ({len(result.dependencies)})")
    dep_table.add_column("Ecosystem", style="cyan")
    dep_table.add_column("Count", justify="right")
    dep_table.add_column("Vulnerable", style="red", justify="right")

    by_ecosystem: Dict[str, Dict[str, int]] = {}
    for dep in result.dependencies:
        eco = dep.ecosystem
        if eco not in by_ecosystem:
            by_ecosystem[eco] = {"total": 0, "vulnerable": 0}
        by_ecosystem[eco]["total"] += 1
        if dep.vulnerabilities:
            by_ecosystem[eco]["vulnerable"] += 1

    for eco, counts in by_ecosystem.items():
        dep_table.add_row(
            eco,
            str(counts["total"]),
            str(counts["vulnerable"]) if counts["vulnerable"] else "-",
        )

    console.print(dep_table)

    if result.vulnerabilities:
        console.print(f"\n[bold red]Vulnerable Dependencies ({len(result.vulnerabilities)}):[/bold red]\n")

        vuln_table = Table()
        vuln_table.add_column("Package", style="cyan")
        vuln_table.add_column("Version", style="dim")
        vuln_table.add_column("CVE", style="red")
        vuln_table.add_column("Severity", style="bold")
        vuln_table.add_column("Fixed In", style="green")

        for vuln in result.vulnerabilities[:20]:
            severity_style = {
                "critical": "red bold",
                "high": "red",
                "medium": "yellow",
                "low": "dim",
            }.get(vuln.severity, "white")

            vuln_table.add_row(
                vuln.package_name,
                vuln.installed_version,
                vuln.cve_id or "N/A",
                f"[{severity_style}]{vuln.severity.upper()}[/{severity_style}]",
                vuln.fixed_version or "Unknown",
            )

        console.print(vuln_table)

        if len(result.vulnerabilities) > 20:
            console.print(f"\n[dim]... and {len(result.vulnerabilities) - 20} more vulnerabilities[/dim]")

    if result.license_issues:
        console.print(f"\n[bold yellow]License Issues ({len(result.license_issues)}):[/bold yellow]")

        for issue in result.license_issues[:10]:
            console.print(f"  [yellow]•[/yellow] {issue.package_name}: {issue.license} - {issue.issue}")

    if output:
        if format == "sbom":
            analyzer.generate_sbom(result, output)
            console.print(f"\n[green]✓[/green] SBOM saved to {output}")
        elif format == "html":
            analyzer.export_html(result, output)
            console.print(f"\n[green]✓[/green] HTML report saved to {output}")
        else:
            with open(output, "w") as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
            console.print(f"\n[green]✓[/green] Report saved to {output}")

    critical_vulns = len([v for v in result.vulnerabilities if v.severity == "critical"])
    if critical_vulns:
        raise SystemExit(2)
    elif result.vulnerabilities:
        raise SystemExit(1)
    raise SystemExit(0)


@security.command()
@click.argument("project_path", type=Path)
@click.option("--output", "-o", type=Path, required=True, help="Output SBOM file path")
@click.option("--format", "-f", type=click.Choice(["cyclonedx", "spdx"]), default="cyclonedx")
def sbom(project_path: Path, output: Path, format: str) -> None:
    """
    Generate Software Bill of Materials (SBOM).

    Creates a comprehensive inventory of all dependencies.

    Example:
        observe security sbom ./project -o sbom.json
        observe security sbom ./app -o sbom.xml --format spdx
    """
    if not validate_path(project_path):
        raise SystemExit(1)

    console.print(Panel.fit(f"SBOM Generation ({format.upper()})", style="bold cyan"))

    analyzer = SupplyChainAnalyzer()

    with console.status("[cyan]Generating SBOM..."):
        result = analyzer.analyze(project_path, check_vulnerabilities=False)
        analyzer.generate_sbom(result, output, format=format)

    console.print(f"\n[green]✓[/green] SBOM generated: {output}")
    console.print(f"[dim]Format: {format.upper()}[/dim]")
    console.print(f"[dim]Components: {len(result.dependencies)}[/dim]")

    raise SystemExit(0)
