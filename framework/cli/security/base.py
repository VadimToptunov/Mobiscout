"""
Base Security CLI Module

Shared utilities, console instance, and main security CLI group.
"""

from pathlib import Path
from typing import Optional, List, Any, Dict

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from framework.security.scanner import (
    SecurityScanner,
    SeverityLevel,
    SecurityScanResult,
)
from framework.security.advanced_security import RiskLevel

# Shared console instance for all security commands
console = Console()


def get_severity_style(severity: SeverityLevel) -> str:
    """Get rich style for severity level."""
    return {
        SeverityLevel.CRITICAL: "red",
        SeverityLevel.HIGH: "yellow",
        SeverityLevel.MEDIUM: "blue",
        SeverityLevel.LOW: "dim",
    }.get(severity, "white")


def get_risk_style(risk_level: RiskLevel) -> str:
    """Get rich style for risk level."""
    return {
        RiskLevel.CRITICAL: "red bold",
        RiskLevel.HIGH: "red",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.LOW: "dim",
        RiskLevel.INFO: "blue",
    }.get(risk_level, "white")


def validate_path(path: Path, must_exist: bool = True) -> bool:
    """Validate path and print error if not found."""
    if must_exist and not path.exists():
        console.print(f"[red]✗[/red] Path not found: {path}")
        return False
    return True


def print_scan_summary(result: SecurityScanResult) -> None:
    """Print security scan summary."""
    console.print(f"[bold]Security Scan Results: {result.app_name}[/bold]")
    console.print(f"Platform: {result.platform} | Version: {result.app_version}\n")

    table = Table()
    table.add_column("Severity", style="cyan")
    table.add_column("Count", justify="right", style="bold")

    severity_counts = [
        ("Critical", result.critical_count, "red"),
        ("High", result.high_count, "yellow"),
        ("Medium", result.medium_count, "blue"),
        ("Low", result.low_count, "dim"),
    ]

    for severity, count, style in severity_counts:
        if count > 0:
            table.add_row(severity, f"[{style}]{count}[/{style}]")
        else:
            table.add_row(severity, "[dim]0[/dim]")

    console.print(table)

    # Overall risk level
    if result.critical_count > 0:
        risk = "[red bold]CRITICAL RISK[/red bold]"
    elif result.high_count > 0:
        risk = "[yellow bold]HIGH RISK[/yellow bold]"
    elif result.medium_count > 0:
        risk = "[blue]MEDIUM RISK[/blue]"
    else:
        risk = "[green]LOW RISK[/green]"

    console.print(f"\nRisk Level: {risk}")


def create_progress_context():
    """Create a progress context with spinner."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    )


def save_json_report(data: Any, output_path: Path) -> None:
    """Save data as JSON report."""
    import json
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def exit_with_severity(critical_count: int, high_count: int = 0) -> None:
    """Exit with appropriate code based on severity counts."""
    if critical_count > 0:
        raise SystemExit(2)
    elif high_count > 0:
        raise SystemExit(1)
    raise SystemExit(0)


@click.group()
def security() -> None:
    """
    Security scanning commands.

    Automated security testing following OWASP Mobile guidelines.
    """
    pass
