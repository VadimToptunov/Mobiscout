"""
Basic Security CLI Commands

Core security scanning commands: scan, audit, list, compare.
"""

from pathlib import Path
from typing import Optional
import json

import click
from rich.panel import Panel
from rich.table import Table

from framework.security.scanner import SecurityScanner, SeverityLevel
from framework.cli.security.base import (
    security,
    console,
    validate_path,
    print_scan_summary,
    get_severity_style,
)


@security.command()
@click.argument("app_path", type=Path)
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), required=True, help="Platform")
@click.option("--app-name", "-n", required=True, help="Application name")
@click.option("--app-version", "-v", default="1.0", help="Application version")
@click.option("--output", "-o", type=Path, help="Output report path")
@click.option("--format", "-f", type=click.Choice(["json", "html"]), default="json", help="Report format")
def scan(
    app_path: Path,
    platform: str,
    app_name: str,
    app_version: str,
    output: Optional[Path],
    format: str,
) -> None:
    """
    Scan mobile application for security vulnerabilities.

    APP_PATH: Path to APK or IPA file

    Example:
        observe security scan app.apk --platform android --app-name MyApp
        observe security scan app.ipa --platform ios --app-name MyApp -o report.json
    """
    if not validate_path(app_path):
        raise SystemExit(1)

    console.print(f"[cyan]→[/cyan] Scanning {app_path}...\n")

    scanner = SecurityScanner()

    if platform == "android":
        result = scanner.scan_android(app_path, app_name, app_version)
    else:
        result = scanner.scan_ios(app_path, app_name, app_version)

    print_scan_summary(result)

    if output:
        scanner.generate_report(result, output, format)
        console.print(f"\n[green]✓[/green] Report saved to {output}")

    if result.critical_count > 0:
        raise SystemExit(2)
    elif result.high_count > 0:
        raise SystemExit(1)
    else:
        raise SystemExit(0)


@security.command()
@click.argument("app_path", type=Path)
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), required=True, help="Platform")
@click.option("--app-name", "-n", required=True, help="Application name")
@click.option("--app-version", "-v", default="1.0", help="Application version")
@click.option("--severity", "-s", type=click.Choice(["critical", "high", "medium", "low"]), help="Filter by severity")
def audit(
    app_path: Path,
    platform: str,
    app_name: str,
    app_version: str,
    severity: Optional[str],
) -> None:
    """
    Quick security audit with detailed findings.

    Example:
        observe security audit app.apk -p android -n MyApp
        observe security audit app.apk -p android -n MyApp --severity high
    """
    if not validate_path(app_path):
        raise SystemExit(1)

    scanner = SecurityScanner()

    if platform == "android":
        result = scanner.scan_android(app_path, app_name, app_version)
    else:
        result = scanner.scan_ios(app_path, app_name, app_version)

    findings = result.findings
    if severity:
        severity_enum = {
            "critical": SeverityLevel.CRITICAL,
            "high": SeverityLevel.HIGH,
            "medium": SeverityLevel.MEDIUM,
            "low": SeverityLevel.LOW,
        }[severity]
        findings = [f for f in findings if f.severity == severity_enum]

    for finding in findings:
        severity_style = get_severity_style(finding.severity)

        panel = Panel(
            f"[bold]{finding.description}[/bold]\n\n"
            f"[dim]Category:[/dim] {finding.category.value}\n"
            f"[dim]Location:[/dim] {finding.location}\n\n"
            f"[cyan]Recommendation:[/cyan]\n{finding.recommendation}",
            title=f"[{severity_style}]{finding.severity.value.upper()}[/{severity_style}] {finding.title}",
            border_style=severity_style,
        )
        console.print(panel)
        console.print()


@security.command(name="list")
def list_checks() -> None:
    """
    List available security checks.

    Example:
        observe security list
    """
    table = Table(title="OWASP Mobile Security Checks")
    table.add_column("Category", style="cyan")
    table.add_column("Description", style="dim")

    checks = [
        ("M1: Improper Platform Usage", "Misuse of platform features or security controls"),
        ("M2: Insecure Data Storage", "Sensitive data stored insecurely"),
        ("M3: Insecure Communication", "Unencrypted or weak network communication"),
        ("M4: Insecure Authentication", "Weak authentication mechanisms"),
        ("M5: Insufficient Cryptography", "Weak or broken cryptography"),
        ("M6: Insecure Authorization", "Poor authorization checks"),
        ("M7: Client Code Quality", "Code-level vulnerabilities"),
        ("M8: Code Tampering", "Binary patching, hooking, modification"),
        ("M9: Reverse Engineering", "Analysis of app binaries"),
        ("M10: Extraneous Functionality", "Hidden backdoors or debug code"),
    ]

    for category, description in checks:
        table.add_row(category, description)

    console.print(table)


@security.command()
@click.argument("app_name")
@click.argument("v1_report", type=Path)
@click.argument("v2_report", type=Path)
def compare(app_name: str, v1_report: Path, v2_report: Path) -> None:
    """
    Compare security reports between versions.

    Example:
        observe security compare MyApp v1_report.json v2_report.json
    """
    if not v1_report.exists() or not v2_report.exists():
        console.print("[red]✗[/red] Report file(s) not found")
        raise SystemExit(1)

    with open(v1_report, "r") as f:
        v1_data = json.load(f)

    with open(v2_report, "r") as f:
        v2_data = json.load(f)

    v1_summary = v1_data["summary"]
    v2_summary = v2_data["summary"]

    console.print(f"[bold cyan]Security Comparison: {app_name}[/bold cyan]\n")

    table = Table()
    table.add_column("Severity", style="cyan")
    table.add_column("Version 1", justify="right")
    table.add_column("Version 2", justify="right")
    table.add_column("Change", justify="right")

    for severity in ["critical", "high", "medium", "low"]:
        v1_count = v1_summary[severity]
        v2_count = v2_summary[severity]
        change = v2_count - v1_count

        if change > 0:
            change_str = f"[red]+{change}[/red]"
        elif change < 0:
            change_str = f"[green]{change}[/green]"
        else:
            change_str = "[dim]0[/dim]"

        table.add_row(
            severity.title(),
            str(v1_count),
            str(v2_count),
            change_str,
        )

    console.print(table)

    total_v1 = v1_summary["total_findings"]
    total_v2 = v2_summary["total_findings"]

    if total_v2 < total_v1:
        console.print("\n[green]✓[/green] Security improved!")
    elif total_v2 > total_v1:
        console.print("\n[red]✗[/red] Security degraded!")
    else:
        console.print("\n[dim]No change in security posture[/dim]")
