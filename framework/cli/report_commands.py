"""
Report Generation CLI Commands

Generate professional test reports in multiple formats.
"""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from framework.reporting.report_generator import (
    ReportGenerator,
    ReportFormat,
    TestSuiteResult,
    TestStatus,
)

console = Console()


@click.group()
def report() -> None:
    """
    Test report generation commands.
    
    Generate professional reports in multiple formats.
    """
    pass


@report.command()
@click.option(
    "--junit-xml",
    "-j",
    type=Path,
    help="JUnit XML input file",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["html", "markdown", "json"]),
    default="html",
    help="Report format",
)
@click.option(
    "--output",
    "-o",
    type=Path,
    required=True,
    help="Output file path",
)
def generate(
        junit_xml: Optional[Path],
        format: str,
        output: Path,
) -> None:
    """
    Generate test report from JUnit XML.
    
    Example:
        observe report generate --junit-xml results.xml --output report.html
        observe report generate -j results.xml -f markdown -o REPORT.md
        observe report generate -j results.xml -f json -o report.json
    """
    if not junit_xml or not junit_xml.exists():
        console.print("[red]✗[/red] JUnit XML file not found")
        raise SystemExit(1)

    console.print(f"[cyan]→[/cyan] Parsing {junit_xml}...")

    try:
        generator = ReportGenerator()
        suite = generator.from_junit_xml(junit_xml)

        console.print(f"[cyan]→[/cyan] Generating {format.upper()} report...")

        report_format = {
            "html": ReportFormat.HTML,
            "markdown": ReportFormat.MARKDOWN,
            "json": ReportFormat.JSON,
        }[format]

        generator.generate(suite, output, report_format)

        console.print(f"[green]✓[/green] Report generated: {output}")

        # Show summary
        _print_summary(suite)

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise SystemExit(1)


@report.command()
@click.argument("junit_xml", type=Path)
def summary(junit_xml: Path) -> None:
    """
    Show test summary from JUnit XML.
    
    Example:
        observe report summary results.xml
    """
    if not junit_xml.exists():
        console.print("[red]✗[/red] JUnit XML file not found")
        raise SystemExit(1)

    try:
        generator = ReportGenerator()
        suite = generator.from_junit_xml(junit_xml)

        _print_summary(suite)

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise SystemExit(1)


@report.command(name="list")
def list_formats() -> None:
    """
    List available report formats.
    
    Example:
        observe report list
    """
    table = Table(title="Available Report Formats")
    table.add_column("Format", style="cyan")
    table.add_column("Extension", style="green")
    table.add_column("Features", style="dim")

    table.add_row(
        "HTML",
        ".html",
        "Interactive, charts, screenshots, modern UI",
    )
    table.add_row(
        "Markdown",
        ".md",
        "GitHub/GitLab friendly, tables, code blocks",
    )
    table.add_row(
        "JSON",
        ".json",
        "Machine-readable, structured data",
    )

    console.print(table)


def _print_summary(suite: TestSuiteResult) -> None:
    """Print test suite summary"""
    # Statistics table
    table = Table(title=f"Test Summary: {suite.name}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Total Tests", str(suite.total_count))
    table.add_row("Passed", str(suite.passed_count))
    table.add_row("Failed", str(suite.failed_count))
    table.add_row("Skipped", str(suite.skipped_count))
    table.add_row("Pass Rate", f"{suite.pass_rate:.1f}%")
    table.add_row("Duration", f"{suite.duration:.2f}s")

    console.print(table)

    # Failed tests
    if suite.failed_count > 0:
        console.print("\n[bold red]Failed Tests:[/bold red]")
        for test in suite.tests:
            if test.status == TestStatus.FAILED:
                console.print(f"  • [red]{test.name}[/red]")
                if test.error_message:
                    console.print(f"    [dim]{test.error_message[:100]}...[/dim]")


if __name__ == "__main__":
    report()
