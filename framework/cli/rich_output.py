"""
Rich CLI helpers for beautiful terminal output.
"""

from typing import Any, Dict, List, Optional

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
    ║   📱 Mobile Test Recorder                                 ║
    ║                                                           ║
    ║   Intelligent Mobile Testing Platform                    ║
    ║   Observe • Analyze • Automate                           ║
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
