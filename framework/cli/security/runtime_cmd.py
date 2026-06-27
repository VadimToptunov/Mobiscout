"""
Runtime Protection Analysis CLI Commands

Commands: runtime, protections
"""

from pathlib import Path
from typing import Optional
import json

import click
from rich.panel import Panel
from rich.table import Table

from framework.security.runtime_protection import RuntimeProtectionAnalyzer
from framework.cli.security.base import (
    security,
    console,
    validate_path,
    create_progress_context,
)


@security.command(name="runtime")
@click.argument("app_path", type=Path)
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), required=True)
@click.option("--output", "-o", type=Path, help="Output report path")
@click.option("--format", "-f", type=click.Choice(["json", "html"]), default="json")
def runtime(
    app_path: Path,
    platform: str,
    output: Optional[Path],
    format: str,
) -> None:
    """
    Analyze runtime protection mechanisms.

    Checks for root/jailbreak detection, anti-debugging, anti-tampering, etc.

    Example:
        observe security runtime app.apk --platform android
        observe security runtime app.ipa -p ios -o runtime_report.json
    """
    if not validate_path(app_path):
        raise SystemExit(1)

    console.print(
        Panel.fit(
            f"Runtime Protection Analysis\n\n" f"App: {app_path.name}\n" f"Platform: {platform.upper()}",
            style="bold red",
        )
    )

    analyzer = RuntimeProtectionAnalyzer()

    with create_progress_context() as progress:
        task = progress.add_task("Analyzing runtime protections...", total=None)
        result = analyzer.analyze(app_path, platform)
        progress.update(task, completed=True)

    console.print()
    console.print(Panel.fit("Runtime Protection Results", style="bold green"))

    protection_table = Table(title="Protection Mechanisms")
    protection_table.add_column("Protection", style="cyan")
    protection_table.add_column("Status", style="bold", justify="center")
    protection_table.add_column("Strength", justify="center")
    protection_table.add_column("Details", style="dim")

    protections = [
        ("Root/Jailbreak Detection", result.root_detection),
        ("Emulator Detection", result.emulator_detection),
        ("Debug Detection", result.debug_detection),
        ("Tamper Detection", result.tamper_detection),
        ("Hook Detection (Frida/Xposed)", result.hook_detection),
        ("SSL Pinning", result.ssl_pinning),
        ("Code Obfuscation", result.obfuscation),
    ]

    for name, protection in protections:
        if protection.detected:
            status = "[green]Detected[/green]"
            strength_color = {"strong": "green", "medium": "yellow", "weak": "red"}.get(protection.strength, "white")
            strength = f"[{strength_color}]{protection.strength.upper()}[/{strength_color}]"
        else:
            status = "[red]Missing[/red]"
            strength = "[dim]-[/dim]"

        protection_table.add_row(
            name,
            status,
            strength,
            (
                protection.details[:30] + "..."
                if protection.details and len(protection.details) > 30
                else (protection.details or "-")
            ),
        )

    console.print(protection_table)

    detected_count = sum(1 for _, p in protections if p.detected)
    score = (detected_count / len(protections)) * 100

    if score >= 80:
        score_style = "green bold"
        verdict = "EXCELLENT"
    elif score >= 60:
        score_style = "yellow bold"
        verdict = "GOOD"
    elif score >= 40:
        score_style = "yellow"
        verdict = "MODERATE"
    else:
        score_style = "red bold"
        verdict = "WEAK"

    console.print(f"\n[bold]Protection Score:[/bold] [{score_style}]{score:.0f}% - {verdict}[/{score_style}]")

    if result.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in result.recommendations[:5]:
            console.print(f"  [cyan]•[/cyan] {rec}")

    if result.bypass_methods:
        console.print(f"\n[bold red]Potential Bypass Methods ({len(result.bypass_methods)}):[/bold red]")
        for bypass in result.bypass_methods[:5]:
            console.print(f"  [red]•[/red] {bypass.method}: {bypass.description}")

    if output:
        if format == "html":
            analyzer.export_html(result, output)
        else:
            with open(output, "w") as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
        console.print(f"\n[green]✓[/green] Report saved to {output}")

    if score < 40:
        raise SystemExit(1)
    raise SystemExit(0)


@security.command()
@click.argument("app_path", type=Path)
@click.option("--platform", "-p", type=click.Choice(["android", "ios"]), required=True)
def protections(app_path: Path, platform: str) -> None:
    """
    Quick check for runtime protections.

    Rapidly scans for common protection mechanisms.

    Example:
        observe security protections app.apk -p android
        observe security protections app.ipa -p ios
    """
    if not validate_path(app_path):
        raise SystemExit(1)

    console.print(Panel.fit(f"Quick Protection Check: {app_path.name}", style="bold cyan"))

    analyzer = RuntimeProtectionAnalyzer()

    with console.status("[cyan]Checking protections..."):
        result = analyzer.quick_check(app_path, platform)

    console.print()

    checks = [
        ("Root/Jailbreak Detection", result.has_root_detection, "Prevents running on compromised devices"),
        ("Emulator Detection", result.has_emulator_detection, "Prevents analysis in emulators"),
        ("Debug Detection", result.has_debug_detection, "Detects attached debuggers"),
        ("Tamper Detection", result.has_tamper_detection, "Verifies app integrity"),
        ("SSL Pinning", result.has_ssl_pinning, "Prevents MITM attacks"),
        ("Code Obfuscation", result.has_obfuscation, "Makes reverse engineering harder"),
    ]

    for name, detected, description in checks:
        if detected:
            console.print(f"[green]✓[/green] {name}")
            console.print(f"  [dim]{description}[/dim]")
        else:
            console.print(f"[red]✗[/red] {name}")
            console.print(f"  [dim]{description}[/dim]")

    detected_count = sum(1 for _, d, _ in checks if d)
    console.print(f"\n[bold]Protection Coverage:[/bold] {detected_count}/{len(checks)}")

    if detected_count < len(checks) // 2:
        console.print("[red]Application lacks basic protections![/red]")
        raise SystemExit(1)

    raise SystemExit(0)
