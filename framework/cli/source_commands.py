"""``mobiscout source`` — static analysis of app source to plan a crawl.

Reads (never executes) an Android/Kotlin project and hypothesises its structure —
Compose screens, tagged UI elements, navigation routes, Retrofit endpoints — so a
crawl (or a human) knows what to expect before touching a device. A different kind
of analysis from ``security`` (which scans for vulnerabilities); this maps the app.
"""

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from framework.cli.rich_output import print_header, print_info, print_success

console = Console()


@click.group(name="source")
def source() -> None:
    """🗺️  Analyze app source to map its structure (crawl planning)."""


@source.command()
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--output", "-o", type=click.Path(), default=None, help="Write the full analysis as JSON here.")
def analyze(source_dir: str, output: Optional[str]) -> None:
    """Statically analyze an Android/Kotlin project's structure."""
    from framework.analyzers.android_analyzer import AndroidAnalyzer

    print_header("Analyzing source", source_dir)

    result = AndroidAnalyzer().analyze(source_dir)

    print_info(
        f"Analyzed {result.files_analyzed} Kotlin file(s): "
        f"{len(result.screens)} screen(s), {len(result.ui_elements)} element(s), "
        f"{len(result.navigation)} route(s), {len(result.api_endpoints)} API endpoint(s)"
    )
    for warning in result.warnings:
        print_info(f"⚠️  {warning}")

    if result.screens:
        table = Table(title="Screens")
        table.add_column("Name", style="cyan")
        table.add_column("Composable")
        table.add_column("Route")
        for screen in result.screens:
            table.add_row(screen.name, screen.composable_name or "-", screen.route or "-")
        console.print(table)

    if result.api_endpoints:
        table = Table(title="API endpoints")
        table.add_column("Method", style="cyan")
        table.add_column("Path")
        table.add_column("Function")
        for endpoint in result.api_endpoints:
            table.add_row(endpoint.method, endpoint.path, endpoint.function_name)
        console.print(table)

    if output:
        Path(output).write_text(json.dumps(result.model_dump(), indent=2, default=str), encoding="utf-8")
        print_success(f"✅ Full analysis written to {output}")
