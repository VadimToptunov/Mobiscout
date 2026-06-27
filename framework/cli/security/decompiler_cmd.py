"""
Decompilation & Reverse Engineering CLI Commands

Commands: decompile, strings
"""

from pathlib import Path
from typing import Optional, Dict, List

import click
from rich.panel import Panel
from rich.table import Table

from framework.security.decompiler import Decompiler
from framework.cli.security.base import (
    security,
    console,
    validate_path,
    create_progress_context,
)


@security.command()
@click.argument("binary_path", type=Path)
@click.option("--output", "-o", type=Path, help="Output directory for decompiled files")
@click.option("--extract-strings/--no-strings", default=True, help="Extract strings from binary")
@click.option("--analyze-native/--no-native", default=True, help="Analyze native libraries")
def decompile(
    binary_path: Path,
    output: Optional[Path],
    extract_strings: bool,
    analyze_native: bool,
) -> None:
    """
    Decompile and analyze mobile application binary.

    Supports APK (Android) and IPA (iOS) files.

    Example:
        observe security decompile app.apk
        observe security decompile app.ipa -o ./decompiled
        observe security decompile app.apk --extract-strings --analyze-native
    """
    if not validate_path(binary_path):
        raise SystemExit(1)

    platform = "android" if binary_path.suffix.lower() == ".apk" else "ios"

    console.print(
        Panel.fit(
            f"Binary Decompilation & Analysis\n\n"
            f"File: {binary_path.name}\n"
            f"Platform: {platform.upper()}\n"
            f"String Extraction: {'Enabled' if extract_strings else 'Disabled'}\n"
            f"Native Analysis: {'Enabled' if analyze_native else 'Disabled'}",
            style="bold magenta",
        )
    )

    decompiler = Decompiler()

    with create_progress_context() as progress:
        task = progress.add_task("Decompiling binary...", total=None)
        result = decompiler.decompile(
            binary_path,
            output_dir=output,
            extract_strings=extract_strings,
            analyze_native=analyze_native,
        )
        progress.update(task, completed=True)

    console.print()
    console.print(Panel.fit("Decompilation Results", style="bold green"))

    info_table = Table(title="Binary Information")
    info_table.add_column("Property", style="cyan")
    info_table.add_column("Value", style="white")

    info_table.add_row("Package", result.package_name)
    info_table.add_row("Version", result.version)
    info_table.add_row("Min SDK", str(result.min_sdk) if result.min_sdk else "N/A")
    info_table.add_row("Target SDK", str(result.target_sdk) if result.target_sdk else "N/A")
    info_table.add_row("SHA256", result.sha256[:32] + "...")
    info_table.add_row("Size", f"{result.size_bytes / 1024 / 1024:.2f} MB")

    console.print(info_table)

    if result.protections:
        console.print("\n[bold]Protection Mechanisms Detected:[/bold]")

        protection_table = Table()
        protection_table.add_column("Protection", style="cyan")
        protection_table.add_column("Status", style="bold")
        protection_table.add_column("Details", style="dim")

        for prot in result.protections:
            status_style = "green" if prot.detected else "red"
            status = "Detected" if prot.detected else "Not Found"
            protection_table.add_row(
                prot.name,
                f"[{status_style}]{status}[/{status_style}]",
                prot.details[:40] if prot.details else "-",
            )

        console.print(protection_table)

    if result.interesting_strings:
        console.print(f"\n[bold]Interesting Strings Found ({len(result.interesting_strings)}):[/bold]")

        for string_info in result.interesting_strings[:15]:
            category_style = {
                "url": "blue",
                "api_key": "red",
                "password": "red",
                "email": "yellow",
                "ip_address": "cyan",
                "secret": "red",
            }.get(string_info.category, "white")

            console.print(
                f"  [{category_style}]•[/{category_style}] [{category_style}]{string_info.category}[/{category_style}]: {string_info.value[:60]}..."
            )

        if len(result.interesting_strings) > 15:
            console.print(f"  [dim]... and {len(result.interesting_strings) - 15} more[/dim]")

    if result.native_libs:
        console.print(f"\n[bold]Native Libraries ({len(result.native_libs)}):[/bold]")

        for lib in result.native_libs[:10]:
            arch_str = ", ".join(lib.architectures) if lib.architectures else "Unknown"
            console.print(f"  [cyan]•[/cyan] {lib.name} ({arch_str})")

    if result.security_findings:
        console.print(f"\n[bold red]Security Findings ({len(result.security_findings)}):[/bold red]")

        for finding in result.security_findings[:10]:
            severity_style = "red" if finding.severity in ["critical", "high"] else "yellow"
            console.print(
                f"  [{severity_style}]•[/{severity_style}] [{severity_style}]{finding.title}[/{severity_style}]"
            )
            console.print(f"    {finding.description}")

    if output:
        console.print(f"\n[green]✓[/green] Decompiled files saved to {output}")

    raise SystemExit(0)


@security.command()
@click.argument("binary_path", type=Path)
@click.option("--output", "-o", type=Path, help="Output file for strings")
@click.option("--min-length", "-m", type=int, default=8, help="Minimum string length")
@click.option("--filter", "-f", type=click.Choice(["all", "urls", "secrets", "emails", "ips"]), default="all")
def strings(
    binary_path: Path,
    output: Optional[Path],
    min_length: int,
    filter: str,
) -> None:
    """
    Extract strings from binary.

    Extracts and categorizes interesting strings from APK/IPA files.

    Example:
        observe security strings app.apk
        observe security strings app.ipa -o strings.txt --filter secrets
        observe security strings app.apk --min-length 12
    """
    if not validate_path(binary_path):
        raise SystemExit(1)

    console.print(Panel.fit(f"String Extraction: {binary_path.name}", style="bold cyan"))

    decompiler = Decompiler()

    with console.status("[cyan]Extracting strings..."):
        strings_list = decompiler.extract_strings(binary_path, min_length=min_length)

    if filter != "all":
        filter_map = {
            "urls": ["url", "endpoint"],
            "secrets": ["api_key", "password", "secret", "token"],
            "emails": ["email"],
            "ips": ["ip_address"],
        }
        categories = filter_map.get(filter, [])
        strings_list = [s for s in strings_list if s.category in categories]

    if not strings_list:
        console.print("[dim]No strings found matching criteria[/dim]")
        raise SystemExit(0)

    console.print(f"\n[bold]Found {len(strings_list)} strings[/bold]\n")

    by_category: Dict[str, List] = {}
    for s in strings_list:
        if s.category not in by_category:
            by_category[s.category] = []
        by_category[s.category].append(s)

    for category, cat_strings in sorted(by_category.items()):
        category_style = {
            "url": "blue",
            "api_key": "red",
            "password": "red",
            "email": "yellow",
            "ip_address": "cyan",
            "secret": "red",
        }.get(category, "white")

        console.print(f"[{category_style}][bold]{category.upper()}[/bold][/{category_style}] ({len(cat_strings)})")

        for s in cat_strings[:10]:
            console.print(f"  {s.value[:80]}{'...' if len(s.value) > 80 else ''}")

        if len(cat_strings) > 10:
            console.print(f"  [dim]... and {len(cat_strings) - 10} more[/dim]")
        console.print()

    if output:
        with open(output, "w") as f:
            for s in strings_list:
                f.write(f"[{s.category}] {s.value}\n")
        console.print(f"\n[green]✓[/green] Strings saved to {output}")

    raise SystemExit(0)
