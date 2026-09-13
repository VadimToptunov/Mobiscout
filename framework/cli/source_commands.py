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
from rich.table import Table

from framework.cli.rich_output import print_header, print_info, print_success, console


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


@source.command()
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["mermaid", "dot", "json"]),
    default="mermaid",
    help="Graph export format (default: mermaid).",
)
@click.option("--output", "-o", type=click.Path(), default=None, help="Write the graph to this file instead of stdout.")
def graph(source_dir: str, fmt: str, output: Optional[str]) -> None:
    """Build the app's interaction graph from source (no device).

    Statically maps screens and the navigation between them (Android/Kotlin or
    iOS/Swift, auto-detected) into the same graph a live crawl produces — so you
    can see the predicted structure, and unreachable / dead-end screens, before
    touching a device.
    """
    from framework.crawler.graph import to_dot, to_json, to_mermaid
    from framework.crawler.source_graph import analyze_source_tree, source_graph

    print_header("Building source graph", source_dir)

    analysis = analyze_source_tree(source_dir)
    g = source_graph(analysis)

    dead = set(g.dead_ends())
    unreachable = set(g.unreachable())
    print_info(
        f"{len(g.nodes)} screen(s), {len(g.edges)} navigation edge(s); "
        f"{len(unreachable)} unreachable, {len(dead)} dead-end"
    )

    if g.nodes:
        table = Table(title="Screens")
        table.add_column("Name", style="cyan")
        table.add_column("Elements", justify="right")
        table.add_column("Note")
        for node in g.nodes:
            note = "entry" if node.is_entry else ("unreachable" if node.id in unreachable else "")
            if node.id in dead and not node.is_entry:
                note = (note + " · dead-end").strip(" ·")
            table.add_row(node.name or f"Screen {node.id}", str(node.element_count), note or "-")
        console.print(table)

    if g.edges:
        by_id = {n.id: (n.name or f"Screen {n.id}") for n in g.nodes}
        table = Table(title="Navigation")
        table.add_column("From", style="cyan")
        table.add_column("→")
        table.add_column("To", style="cyan")
        table.add_column("Via")
        for edge in g.edges:
            table.add_row(by_id.get(edge.src, "?"), "→", by_id.get(edge.dst, "?"), edge.label or "-")
        console.print(table)

    rendered = {"mermaid": to_mermaid, "dot": to_dot, "json": to_json}[fmt](g)
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
        print_success(f"✅ Graph ({fmt}) written to {output}")
    else:
        console.print(rendered)
