"""
DAST (Dynamic Application Security Testing) CLI Commands

Commands: dast, ssl, api
"""

from pathlib import Path
from typing import Optional
import json

import click
from rich.panel import Panel
from rich.table import Table

from framework.security.dast_analyzer import DASTAnalyzer
from framework.cli.security.base import (
    security,
    console,
    create_progress_context,
)


@security.command()
@click.argument("target", type=str)
@click.option("--port", "-p", type=int, default=443, help="Target port")
@click.option("--output", "-o", type=Path, help="Output report path")
@click.option("--format", "-f", type=click.Choice(["json", "html"]), default="json")
def dast(target: str, port: int, output: Optional[Path], format: str) -> None:
    """
    Run Dynamic Application Security Testing (DAST).

    Tests running application for SSL/TLS, API security, and session vulnerabilities.

    Example:
        observe security dast api.example.com
        observe security dast 192.168.1.100 --port 8443 -o dast_report.json
    """
    console.print(Panel.fit(
        "Dynamic Application Security Testing (DAST)\n\n"
        f"Target: {target}:{port}\n"
        f"Tests: SSL/TLS, API Security, Session Analysis",
        style="bold yellow"
    ))

    analyzer = DASTAnalyzer()

    with create_progress_context() as progress:
        task = progress.add_task("Running DAST analysis...", total=None)
        result = analyzer.analyze(target, port)
        progress.update(task, completed=True)

    console.print()
    console.print(Panel.fit("DAST Analysis Results", style="bold green"))

    if not result.findings:
        console.print("[green]✓[/green] No vulnerabilities found!")
        raise SystemExit(0)

    table = Table(title=f"Found {len(result.findings)} Issues")
    table.add_column("Category", style="cyan")
    table.add_column("Severity", style="bold")
    table.add_column("Finding")

    for finding in result.findings:
        severity_style = {
            "critical": "red bold",
            "high": "red",
            "medium": "yellow",
            "low": "dim",
        }.get(finding.severity, "white")

        table.add_row(
            finding.category,
            f"[{severity_style}]{finding.severity.upper()}[/{severity_style}]",
            finding.title[:50] + ("..." if len(finding.title) > 50 else ""),
        )

    console.print(table)

    console.print("\n[bold]Detailed Findings:[/bold]\n")

    for finding in result.findings[:10]:
        severity_style = "red" if finding.severity in ["critical", "high"] else "yellow"
        console.print(f"[{severity_style}]•[/{severity_style}] [{severity_style}]{finding.title}[/{severity_style}]")
        console.print(f"  [dim]Category:[/dim] {finding.category}")
        console.print(f"  {finding.description}")
        console.print(f"  [cyan]Recommendation:[/cyan] {finding.recommendation}")
        console.print()

    if output:
        if format == "html":
            analyzer.export_html(result, output)
        else:
            with open(output, 'w') as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Report saved to {output}")

    critical = len([f for f in result.findings if f.severity == "critical"])
    if critical:
        raise SystemExit(2)
    raise SystemExit(1)


@security.command()
@click.argument("host", type=str)
@click.option("--port", "-p", type=int, default=443, help="Target port")
def ssl(host: str, port: int) -> None:
    """
    Analyze SSL/TLS configuration.

    Checks for weak protocols, cipher suites, and certificate issues.

    Example:
        observe security ssl api.example.com
        observe security ssl 192.168.1.100 --port 8443
    """
    console.print(Panel.fit(f"SSL/TLS Analysis: {host}:{port}", style="bold cyan"))

    analyzer = DASTAnalyzer()

    with console.status("[cyan]Analyzing SSL/TLS configuration..."):
        result = analyzer.analyze_ssl(host, port)

    if not result.findings:
        console.print("[green]✓[/green] SSL/TLS configuration is secure!")
        console.print(f"\n[dim]Protocol: {result.protocol}[/dim]")
        console.print(f"[dim]Cipher: {result.cipher_suite}[/dim]")
        console.print(f"[dim]Certificate Valid Until: {result.cert_expiry}[/dim]")
        raise SystemExit(0)

    console.print(f"\n[yellow]Found {len(result.findings)} SSL/TLS issue(s)[/yellow]\n")

    table = Table()
    table.add_column("Severity", style="bold", width=10)
    table.add_column("Issue", style="white")
    table.add_column("Recommendation", style="cyan")

    for finding in result.findings:
        severity_style = {
            "critical": "red",
            "high": "yellow",
            "medium": "blue",
            "low": "dim",
        }.get(finding.severity, "white")

        table.add_row(
            f"[{severity_style}]{finding.severity.upper()}[/{severity_style}]",
            finding.title,
            finding.recommendation[:40] + "...",
        )

    console.print(table)

    raise SystemExit(1)


@security.command()
@click.argument("base_url", type=str)
@click.option("--auth-header", "-a", type=str, help="Authorization header value")
@click.option("--endpoints", "-e", type=Path, help="File with endpoint definitions")
def api(base_url: str, auth_header: Optional[str], endpoints: Optional[Path]) -> None:
    """
    Test API security vulnerabilities.

    Checks for injection, authentication bypass, and IDOR vulnerabilities.

    Example:
        observe security api https://api.example.com
        observe security api https://api.example.com -a "Bearer token123"
        observe security api https://api.example.com -e endpoints.json
    """
    console.print(Panel.fit(f"API Security Testing: {base_url}", style="bold green"))

    analyzer = DASTAnalyzer()

    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header

    endpoint_list = None
    if endpoints and endpoints.exists():
        with open(endpoints) as f:
            endpoint_list = json.load(f)

    with create_progress_context() as progress:
        task = progress.add_task("Testing API endpoints...", total=None)
        result = analyzer.test_api(base_url, headers, endpoint_list)
        progress.update(task, completed=True)

    if not result.findings:
        console.print("[green]✓[/green] No API security issues found!")
        raise SystemExit(0)

    console.print(f"\n[red]Found {len(result.findings)} API vulnerability(ies)[/red]\n")

    for finding in result.findings:
        severity_style = "red" if finding.severity in ["critical", "high"] else "yellow"

        panel = Panel(
            f"[bold]{finding.title}[/bold]\n\n"
            f"[dim]Endpoint:[/dim] {finding.endpoint}\n"
            f"[dim]Method:[/dim] {finding.method}\n"
            f"[dim]Vulnerability:[/dim] {finding.vulnerability_type}\n\n"
            f"{finding.description}\n\n"
            f"[cyan]Recommendation:[/cyan] {finding.recommendation}",
            title=f"[{severity_style}]{finding.severity.upper()}[/{severity_style}]",
            border_style=severity_style,
        )
        console.print(panel)
        console.print()

    raise SystemExit(1)
