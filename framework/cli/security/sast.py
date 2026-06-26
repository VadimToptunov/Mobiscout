"""
SAST (Static Application Security Testing) CLI Commands

Commands: sast, taint
"""

from pathlib import Path
from typing import Optional, Dict, List
import json

import click
from rich.panel import Panel
from rich.table import Table

from framework.security.sast_analyzer import SASTAnalyzer
from framework.cli.security.base import (
    security,
    console,
    validate_path,
    create_progress_context,
)


@security.command()
@click.argument("source_path", type=Path)
@click.option("--language", "-l", type=click.Choice(["python", "java", "kotlin", "swift", "javascript", "all"]), default="all")
@click.option("--output", "-o", type=Path, help="Output report path")
@click.option("--format", "-f", type=click.Choice(["json", "sarif", "html"]), default="json")
@click.option("--taint/--no-taint", default=True, help="Enable taint analysis")
@click.option("--crypto/--no-crypto", default=True, help="Enable cryptography analysis")
def sast(
    source_path: Path,
    language: str,
    output: Optional[Path],
    format: str,
    taint: bool,
    crypto: bool,
) -> None:
    """
    Run Static Application Security Testing (SAST).

    Comprehensive static analysis with taint tracking, control flow analysis,
    and cryptography vulnerability detection.

    Example:
        observe security sast ./src --language python
        observe security sast ./app -l java -o sast_report.sarif --format sarif
        observe security sast ./project --taint --crypto
    """
    if not validate_path(source_path):
        raise SystemExit(1)

    console.print(Panel.fit(
        "Static Application Security Testing (SAST)\n\n"
        f"Source: {source_path}\n"
        f"Language: {language.upper()}\n"
        f"Taint Analysis: {'Enabled' if taint else 'Disabled'}\n"
        f"Crypto Analysis: {'Enabled' if crypto else 'Disabled'}",
        style="bold cyan"
    ))

    analyzer = SASTAnalyzer()

    with create_progress_context() as progress:
        task = progress.add_task("Running SAST analysis...", total=None)
        result = analyzer.analyze(
            source_path,
            language=language if language != "all" else None,
            enable_taint=taint,
            enable_crypto=crypto,
        )
        progress.update(task, completed=True)

    console.print()
    console.print(Panel.fit("SAST Analysis Results", style="bold green"))

    if not result.vulnerabilities:
        console.print("[green]✓[/green] No vulnerabilities found!")
        raise SystemExit(0)

    by_type: Dict[str, List] = {}
    for vuln in result.vulnerabilities:
        vtype = vuln.vulnerability_type.value
        if vtype not in by_type:
            by_type[vtype] = []
        by_type[vtype].append(vuln)

    table = Table(title=f"Found {len(result.vulnerabilities)} Vulnerabilities")
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Critical", style="red", justify="right")
    table.add_column("High", style="yellow", justify="right")

    for vtype, vulns in sorted(by_type.items(), key=lambda x: len(x[1]), reverse=True):
        critical = len([v for v in vulns if v.severity == "critical"])
        high = len([v for v in vulns if v.severity == "high"])
        table.add_row(vtype, str(len(vulns)), str(critical) if critical else "-", str(high) if high else "-")

    console.print(table)

    console.print("\n[bold]Top Findings:[/bold]")
    critical_vulns = [v for v in result.vulnerabilities if v.severity == "critical"]
    high_vulns = [v for v in result.vulnerabilities if v.severity == "high"]

    for vuln in (critical_vulns + high_vulns)[:10]:
        severity_style = "red bold" if vuln.severity == "critical" else "yellow"
        console.print(f"  [{severity_style}]•[/{severity_style}] [{severity_style}]{vuln.vulnerability_type.value}[/{severity_style}]")
        console.print(f"    [dim]File:[/dim] {vuln.file_path}:{vuln.line_number}")
        console.print(f"    [dim]CWE:[/dim] {vuln.cwe_id} | {vuln.description[:60]}...")
        if vuln.taint_flow:
            console.print(f"    [dim]Taint Flow:[/dim] {vuln.taint_flow.source} -> {vuln.taint_flow.sink}")
        console.print()

    if output:
        if format == "sarif":
            analyzer.export_sarif(result, output)
        elif format == "html":
            analyzer.export_html(result, output)
        else:
            with open(output, 'w') as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Report saved to {output}")

    if critical_vulns:
        raise SystemExit(2)
    elif high_vulns:
        raise SystemExit(1)
    raise SystemExit(0)


@security.command()
@click.argument("source_path", type=Path)
@click.option("--output", "-o", type=Path, help="Output report path")
def taint(source_path: Path, output: Optional[Path]) -> None:
    """
    Run taint analysis to track data flow from sources to sinks.

    Identifies injection vulnerabilities by tracing untrusted input.

    Example:
        observe security taint ./src
        observe security taint ./app -o taint_report.json
    """
    if not validate_path(source_path):
        raise SystemExit(1)

    console.print(Panel.fit("Taint Flow Analysis", style="bold magenta"))

    analyzer = SASTAnalyzer()

    with console.status("[cyan]Analyzing taint flows..."):
        result = analyzer.analyze(source_path, enable_taint=True, enable_crypto=False)

    taint_vulns = [v for v in result.vulnerabilities if v.taint_flow]

    if not taint_vulns:
        console.print("[green]✓[/green] No taint flow vulnerabilities found!")
        raise SystemExit(0)

    console.print(f"\n[red]Found {len(taint_vulns)} taint flow issue(s)[/red]\n")

    for vuln in taint_vulns[:15]:
        flow = vuln.taint_flow
        severity_style = "red" if vuln.severity in ["critical", "high"] else "yellow"

        panel = Panel(
            f"[bold]{vuln.vulnerability_type.value}[/bold]\n\n"
            f"[dim]Source:[/dim] {flow.source} (line {flow.source_line})\n"
            f"[dim]Sink:[/dim] {flow.sink} (line {flow.sink_line})\n"
            f"[dim]File:[/dim] {vuln.file_path}\n"
            f"[dim]Path Length:[/dim] {len(flow.path)} nodes\n\n"
            f"[cyan]Flow Path:[/cyan]\n" + " -> ".join(flow.path[:5]) +
            (f" -> ... ({len(flow.path) - 5} more)" if len(flow.path) > 5 else "") +
            f"\n\n[yellow]CWE-{vuln.cwe_id}:[/yellow] {vuln.description}",
            title=f"[{severity_style}]{vuln.severity.upper()}[/{severity_style}]",
            border_style=severity_style,
        )
        console.print(panel)
        console.print()

    if output:
        data = [v.to_dict() for v in taint_vulns]
        with open(output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Report saved to {output}")

    raise SystemExit(1)
