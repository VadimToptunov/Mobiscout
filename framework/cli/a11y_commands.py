"""
Accessibility Testing CLI Commands

Commands for WCAG compliance checking and accessibility testing.
"""

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from framework.analysis.accessibility_analyzer import (
    AccessibilityScanner,
    WCAGLevel,
    A11yViolationSeverity,
)

console = Console()


@click.group()
def a11y() -> None:
    """
    Accessibility testing commands.
    
    Automated WCAG 2.1 compliance checking.
    """
    pass


@a11y.command()
@click.argument("hierarchy_file", type=Path)
@click.option("--app-name", "-a", required=True, help="Application name")
@click.option("--screen", "-s", required=True, help="Screen name")
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), default="android", help="Platform")
@click.option("--wcag-level", "-w", type=click.Choice(["A", "AA", "AAA"]), default="AA", help="WCAG level")
@click.option("--output", "-o", type=Path, help="Output report path")
@click.option("--format", "-f", type=click.Choice(["json", "html"]), default="json", help="Report format")
def scan(
        hierarchy_file: Path,
        app_name: str,
        screen: str,
        platform: str,
        wcag_level: str,
        output: Optional[Path],
        format: str,
) -> None:
    """
    Scan UI hierarchy for accessibility issues.
    
    HIERARCHY_FILE: Path to UI hierarchy JSON file
    
    Example:
        observe a11y scan hierarchy.json --app-name MyApp --screen Login
        observe a11y scan hierarchy.json -a MyApp -s Home --wcag-level AAA
    """
    if not hierarchy_file.exists():
        console.print(f"[red]✗[/red] File not found: {hierarchy_file}")
        raise SystemExit(1)

    console.print(f"[cyan]→[/cyan] Scanning {hierarchy_file}...\n")

    # Load hierarchy
    with open(hierarchy_file, "r") as f:
        hierarchy = json.load(f)

    # Create scanner
    level = {"A": WCAGLevel.A, "AA": WCAGLevel.AA, "AAA": WCAGLevel.AAA}[wcag_level]
    scanner = AccessibilityScanner(wcag_level=level)

    # Scan
    result = scanner.scan_hierarchy(hierarchy, app_name, screen, platform)

    # Print summary
    _print_summary(result)

    # Generate report if requested
    if output:
        scanner.generate_report(result, output, format)
        console.print(f"\n[green]✓[/green] Report saved to {output}")

    # Exit code based on violations
    if result.critical_count > 0:
        raise SystemExit(2)
    elif result.serious_count > 0:
        raise SystemExit(1)
    else:
        raise SystemExit(0)


@a11y.command()
@click.argument("hierarchy_file", type=Path)
@click.option("--app-name", "-a", required=True, help="Application name")
@click.option("--screen", "-s", required=True, help="Screen name")
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), default="android", help="Platform")
@click.option("--wcag-level", "-w", type=click.Choice(["A", "AA", "AAA"]), default="AA", help="WCAG level")
@click.option("--severity", type=click.Choice(["critical", "serious", "moderate", "minor"]), help="Filter by severity")
def audit(
        hierarchy_file: Path,
        app_name: str,
        screen: str,
        platform: str,
        wcag_level: str,
        severity: Optional[str],
) -> None:
    """
    Detailed accessibility audit with violation details.
    
    Example:
        observe a11y audit hierarchy.json -a MyApp -s Login
        observe a11y audit hierarchy.json -a MyApp -s Home --severity critical
    """
    if not hierarchy_file.exists():
        console.print(f"[red]✗[/red] File not found: {hierarchy_file}")
        raise SystemExit(1)

    # Load hierarchy
    with open(hierarchy_file, "r") as f:
        hierarchy = json.load(f)

    # Create scanner
    level = {"A": WCAGLevel.A, "AA": WCAGLevel.AA, "AAA": WCAGLevel.AAA}[wcag_level]
    scanner = AccessibilityScanner(wcag_level=level)

    # Scan
    result = scanner.scan_hierarchy(hierarchy, app_name, screen, platform)

    # Filter by severity if requested
    violations = result.violations
    if severity:
        severity_enum = {
            "critical": A11yViolationSeverity.CRITICAL,
            "serious": A11yViolationSeverity.SERIOUS,
            "moderate": A11yViolationSeverity.MODERATE,
            "minor": A11yViolationSeverity.MINOR,
        }[severity]
        violations = [v for v in violations if v.severity == severity_enum]

    # Print detailed violations
    for violation in violations:
        severity_style = {
            A11yViolationSeverity.CRITICAL: "red",
            A11yViolationSeverity.SERIOUS: "yellow",
            A11yViolationSeverity.MODERATE: "blue",
            A11yViolationSeverity.MINOR: "dim",
        }[violation.severity]

        panel = Panel(
            f"[bold]{violation.description}[/bold]\n\n"
            f"[dim]Element:[/dim] {violation.element}\n"
            f"[dim]Rule:[/dim] {violation.rule_id}\n"
            f"[dim]WCAG:[/dim] {violation.wcag_reference}\n\n"
            f"[cyan]Recommendation:[/cyan]\n{violation.recommendation}\n\n"
            f"[dim]Learn more: {violation.help_url}[/dim]",
            title=f"[{severity_style}]{violation.severity.value.upper()}[/{severity_style}] {violation.title}",
            border_style=severity_style,
        )
        console.print(panel)
        console.print()


@a11y.command(name="list")
def list_checks() -> None:
    """
    List available accessibility checks.
    
    Example:
        observe a11y list
    """
    table = Table(title="Accessibility Checks")
    table.add_column("Rule ID", style="cyan")
    table.add_column("WCAG Level", justify="center")
    table.add_column("Description", style="dim")

    checks = [
        ("color-contrast", "AA", "Color contrast ratios"),
        ("touch-target-size", "AAA", "Minimum touch target size"),
        ("missing-content-description", "A", "Accessibility labels for screen readers"),
        ("text-too-small", "AA", "Minimum text size"),
    ]

    for rule_id, level, description in checks:
        table.add_row(rule_id, level, description)

    console.print(table)

    console.print("\n[bold]WCAG 2.1 Levels:[/bold]")
    console.print("  [cyan]A[/cyan]   - Minimum compliance")
    console.print("  [cyan]AA[/cyan]  - Mid-range compliance (recommended)")
    console.print("  [cyan]AAA[/cyan] - Highest compliance")


@a11y.command()
@click.argument("report1", type=Path)
@click.argument("report2", type=Path)
def compare(report1: Path, report2: Path) -> None:
    """
    Compare two accessibility reports.
    
    Example:
        observe a11y compare v1_report.json v2_report.json
    """
    if not report1.exists() or not report2.exists():
        console.print("[red]✗[/red] Report file(s) not found")
        raise SystemExit(1)

    with open(report1, "r") as f:
        data1 = json.load(f)

    with open(report2, "r") as f:
        data2 = json.load(f)

    summary1 = data1["summary"]
    summary2 = data2["summary"]

    console.print("[bold cyan]Accessibility Comparison[/bold cyan]\n")

    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Report 1", justify="right")
    table.add_column("Report 2", justify="right")
    table.add_column("Change", justify="right")

    for metric in ["compliance_score", "violations", "critical", "serious"]:
        val1 = summary1[metric]
        val2 = summary2[metric]
        change = val2 - val1

        if metric == "compliance_score":
            change_str = f"{change:+.1f}%"
            if change > 0:
                change_str = f"[green]{change_str}[/green]"
            elif change < 0:
                change_str = f"[red]{change_str}[/red]"
        else:
            change_str = f"{change:+d}"
            if change < 0:
                change_str = f"[green]{change_str}[/green]"
            elif change > 0:
                change_str = f"[red]{change_str}[/red]"
            else:
                change_str = "[dim]0[/dim]"

        metric_name = metric.replace("_", " ").title()
        table.add_row(metric_name, str(val1), str(val2), change_str)

    console.print(table)

    # Overall verdict
    score1 = summary1["compliance_score"]
    score2 = summary2["compliance_score"]

    if score2 > score1:
        console.print("\n[green]✓[/green] Accessibility improved!")
    elif score2 < score1:
        console.print("\n[red]✗[/red] Accessibility degraded!")
    else:
        console.print("\n[dim]No change in accessibility[/dim]")


@a11y.command()
@click.argument("report_file", type=Path)
def summary(report_file: Path) -> None:
    """
    Show summary from accessibility report.
    
    Example:
        observe a11y summary report.json
    """
    if not report_file.exists():
        console.print(f"[red]✗[/red] File not found: {report_file}")
        raise SystemExit(1)

    with open(report_file, "r") as f:
        data = json.load(f)

    # Create result object for display
    from framework.analysis.accessibility_analyzer import A11yScanResult, A11yViolation

    result = A11yScanResult(
        app_name=data["app_name"],
        screen_name=data["screen_name"],
        wcag_level=WCAGLevel[data["wcag_level"]],
        pass_count=data["summary"]["passed"],
        total_checks=data["summary"]["total_checks"],
    )

    for v_data in data["violations"]:
        result.violations.append(A11yViolation(
            rule_id=v_data["rule_id"],
            severity=A11yViolationSeverity(v_data["severity"]),
            wcag_level=WCAGLevel[v_data["wcag_level"]],
            title=v_data["title"],
            description=v_data["description"],
            element=v_data["element"],
            recommendation=v_data["recommendation"],
            wcag_reference=v_data.get("wcag_reference", ""),
            help_url=v_data.get("help_url", ""),
        ))

    _print_summary(result)


def _print_summary(result) -> None:
    """Print accessibility scan summary"""
    console.print(f"[bold]Accessibility Scan: {result.app_name}[/bold]")
    console.print(f"Screen: {result.screen_name} | WCAG Level: {result.wcag_level.value}\n")

    # Compliance score
    score_color = "green" if result.compliance_score >= 90 else "yellow" if result.compliance_score >= 70 else "red"
    console.print(f"[bold {score_color}]Compliance Score: {result.compliance_score:.0f}%[/bold {score_color}]\n")

    # Statistics table
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right", style="bold")

    table.add_row("Total Checks", str(result.total_checks))
    table.add_row("Passed", f"[green]{result.pass_count}[/green]")
    table.add_row("Violations", f"[red]{len(result.violations)}[/red]")
    table.add_row("  Critical", f"[red]{result.critical_count}[/red]")
    table.add_row("  Serious", f"[yellow]{result.serious_count}[/yellow]")

    console.print(table)

    # Overall status
    if result.critical_count > 0:
        status = "[red bold]CRITICAL ISSUES[/red bold]"
    elif result.serious_count > 0:
        status = "[yellow bold]NEEDS ATTENTION[/yellow bold]"
    elif result.compliance_score >= 90:
        status = "[green bold]EXCELLENT[/green bold]"
    else:
        status = "[blue]GOOD[/blue]"

    console.print(f"\nStatus: {status}")


if __name__ == "__main__":
    a11y()
