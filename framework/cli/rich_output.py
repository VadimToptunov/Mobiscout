"""
Rich CLI helpers for beautiful terminal output.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

console = Console()


def print_success(message: str) -> None:
    """Print success message with green checkmark."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print error message with red X."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print warning message with yellow triangle."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_info(message: str) -> None:
    """Print info message with blue i."""
    console.print(f"[blue]ℹ[/blue] {message}")


def print_header(title: str, subtitle: Optional[str] = None) -> None:
    """
    Print a beautiful header with title and optional subtitle.

    Args:
        title: Main title
        subtitle: Optional subtitle
    """
    content = f"[bold cyan]{title}[/bold cyan]"
    if subtitle:
        content += f"\n[dim]{subtitle}[/dim]"

    console.print(
        Panel(
            content,
            border_style="cyan",
            box=box.DOUBLE,
            padding=(1, 2),
        )
    )


def print_section(title: str) -> None:
    """Print section header."""
    console.print(f"\n[bold underline cyan]{title}[/bold underline cyan]\n")


def print_table(
    data: List[Dict[str, Any]],
    title: Optional[str] = None,
    columns: Optional[List[str]] = None,
) -> None:
    """
    Print data in a beautiful table.

    Args:
        data: List of dictionaries with data
        title: Optional table title
        columns: Optional list of column names (uses dict keys if not provided)
    """
    if not data:
        print_warning("No data to display")
        return

    # Auto-detect columns if not provided
    if columns is None:
        columns = list(data[0].keys())

    table = Table(title=title, box=box.ROUNDED, show_header=True, header_style="bold magenta")

    for col in columns:
        table.add_column(col.replace("_", " ").title(), style="cyan")

    for row in data:
        table.add_row(*[str(row.get(col, "")) for col in columns])

    console.print(table)


def print_tree(data: Dict[str, Any], root_label: str = "Root") -> None:
    """
    Print hierarchical data as a tree.

    Args:
        data: Nested dictionary or list
        root_label: Label for root node
    """
    tree = Tree(f"[bold cyan]{root_label}[/bold cyan]")

    def add_branch(parent: Tree, data: Any) -> None:
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    branch = parent.add(f"[yellow]{key}[/yellow]")
                    add_branch(branch, value)
                else:
                    parent.add(f"[yellow]{key}:[/yellow] [green]{value}[/green]")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, (dict, list)):
                    branch = parent.add(f"[yellow][{i}][/yellow]")
                    add_branch(branch, item)
                else:
                    parent.add(f"[yellow][{i}]:[/yellow] [green]{item}[/green]")

    add_branch(tree, data)
    console.print(tree)


def print_code(
    code: str,
    language: str = "python",
    line_numbers: bool = True,
    theme: str = "monokai",
) -> None:
    """
    Print syntax-highlighted code.

    Args:
        code: Code to display
        language: Programming language
        line_numbers: Show line numbers
        theme: Syntax theme
    """
    syntax = Syntax(code, language, line_numbers=line_numbers, theme=theme)
    console.print(syntax)


def print_summary(
    title: str,
    stats: Dict[str, Any],
    style: str = "cyan",
) -> None:
    """
    Print a summary box with statistics.

    Args:
        title: Summary title
        stats: Dictionary of statistics to display
        style: Border style color
    """
    content = ""
    for key, value in stats.items():
        label = key.replace("_", " ").title()
        content += f"[bold]{label}:[/bold] [green]{value}[/green]\n"

    console.print(
        Panel(
            content.strip(),
            title=f"[bold]{title}[/bold]",
            border_style=style,
            box=box.ROUNDED,
        )
    )


def create_progress() -> Progress:
    """
    Create a beautiful progress bar.

    Returns:
        Configured Progress instance
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def print_banner() -> None:
    """Print the application banner."""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   📱 Mobiscout                                             ║
    ║                                                           ║
    ║   Intelligent Mobile Testing Platform                    ║
    ║   Scout • Analyze • Automate                           ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


def confirm(message: str, default: bool = False) -> bool:
    """
    Ask for user confirmation with a beautiful prompt.

    Args:
        message: Confirmation message
        default: Default value if user just presses Enter

    Returns:
        User's choice
    """
    choices = "[Y/n]" if default else "[y/N]"
    while True:
        console.print(f"[yellow]❓[/yellow] {message} {choices}: ", end="")
        choice = input().strip().lower()

        if not choice:
            return default
        if choice in ["y", "yes"]:
            return True
        if choice in ["n", "no"]:
            return False

        print_error("Please answer 'yes' or 'no'")


# ---------------------------------------------------------------------------
# Report output dispatch
# ---------------------------------------------------------------------------


def output_format(*choices: str, default: str = "json", help: Optional[str] = None) -> Callable[..., Any]:
    """Reusable ``--format`` / ``-f`` click option.

    ``output_format("json", "html")`` is equivalent to the hand-written
    ``click.option("--format", "-f", type=click.Choice(["json", "html"]), default="json")``.
    Choice order is preserved for both validation and ``--help`` rendering.
    """
    return click.option(
        "--format",
        "-f",
        type=click.Choice(list(choices)),
        default=default,
        help=help,
    )


def write_report(
    data: Any,
    output: Path,
    fmt: str,
    writers: Optional[Mapping[str, Callable[[Path], None]]] = None,
) -> None:
    """Dispatch report writing to a format-specific writer.

    ``writers`` maps a format name to a callable that receives the output path
    and performs the write (typically an analyzer's ``export_html`` / ``export_sarif``
    / SBOM emitter). Any format not present in ``writers`` — in practice ``json`` —
    falls back to serialising ``data`` as pretty JSON, matching the previous
    ``save_json_report`` / inline ``json.dump(..., indent=2, default=str)`` behaviour.
    """
    writer = (writers or {}).get(fmt)
    if writer is not None:
        writer(output)
    else:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Report comparison rendering
# ---------------------------------------------------------------------------


@dataclass
class ComparisonMetric:
    """One row of a :func:`render_comparison` diff table.

    ``key`` is looked up in both report summaries. ``higher_is_better`` flips
    which direction of change is coloured green (improvement) vs red (regression).
    ``percent`` formats the change as ``+1.2%`` (a score) instead of ``+3`` (a count);
    counts additionally render an unchanged value as a dimmed ``0``.
    """

    key: str
    higher_is_better: bool = False
    percent: bool = False


def render_comparison(
    report_a: Mapping[str, Any],
    report_b: Mapping[str, Any],
    metrics: List[ComparisonMetric],
    *,
    title: str,
    columns: Tuple[str, str, str],
    verdict_key: str,
    verdict_higher_is_better: bool,
    verdict_improved: str,
    verdict_degraded: str,
    verdict_unchanged: str,
) -> None:
    """Render a two-report diff table plus an improved/degraded verdict.

    ``report_a`` / ``report_b`` are the two summary mappings. ``columns`` supplies
    the first three column headers (the fourth is always ``Change``). The verdict
    compares ``verdict_key`` across the two reports using ``verdict_higher_is_better``
    and prints one of the three fully-formatted verdict strings (each including any
    desired leading newline and Rich markup).
    """
    console.print(title)

    table = Table()
    table.add_column(columns[0], style="cyan")
    table.add_column(columns[1], justify="right")
    table.add_column(columns[2], justify="right")
    table.add_column("Change", justify="right")

    for metric in metrics:
        val_a = report_a[metric.key]
        val_b = report_b[metric.key]
        change = val_b - val_a

        if metric.higher_is_better:
            good, bad = change > 0, change < 0
        else:
            good, bad = change < 0, change > 0

        if metric.percent:
            change_str = f"{change:+.1f}%"
            if good:
                change_str = f"[green]{change_str}[/green]"
            elif bad:
                change_str = f"[red]{change_str}[/red]"
        else:
            if good:
                change_str = f"[green]{change:+d}[/green]"
            elif bad:
                change_str = f"[red]{change:+d}[/red]"
            else:
                change_str = "[dim]0[/dim]"

        label = metric.key.replace("_", " ").title()
        table.add_row(label, str(val_a), str(val_b), change_str)

    console.print(table)

    verdict_a = report_a[verdict_key]
    verdict_b = report_b[verdict_key]
    if verdict_higher_is_better:
        improved, degraded = verdict_b > verdict_a, verdict_b < verdict_a
    else:
        improved, degraded = verdict_b < verdict_a, verdict_b > verdict_a

    if improved:
        console.print(verdict_improved)
    elif degraded:
        console.print(verdict_degraded)
    else:
        console.print(verdict_unchanged)
