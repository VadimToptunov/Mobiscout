"""
Observability CLI Commands

Commands for metrics export, log tailing, and trace analysis.
"""

import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from framework.observability import (
    ObservabilityManager,
)

console = Console()


@click.group()
def observe_() -> None:
    """
    Observability commands.

    Metrics, logs, and tracing for production monitoring.
    """
    pass


@observe_.command()
@click.option("--format", "-f", type=click.Choice(["prometheus", "json"]), default="prometheus", help="Output format")
@click.option("--output", "-o", type=Path, help="Output file path")
def metrics(format: str, output: Optional[Path]) -> None:
    """
    Export collected metrics.

    Example:
        observe observe metrics --format prometheus --output metrics.txt
        observe observe metrics --format json
    """
    manager = ObservabilityManager.get_instance()

    if format == "prometheus":
        content = manager.metrics.export_prometheus(output)
        if not output:
            console.print("[bold cyan]Prometheus Metrics[/bold cyan]\n")
            console.print(content)
    else:  # json
        import json

        summary = manager.metrics.get_summary()

        if output:
            with open(output, "w") as f:
                json.dump(summary, f, indent=2)
            console.print(f"[green]✓[/green] Metrics exported to {output}")
        else:
            console.print(
                Panel(
                    Syntax(json.dumps(summary, indent=2), "json", theme="monokai"),
                    title="Metrics Summary",
                )
            )


@observe_.command()
@click.option("--log-file", "-f", type=Path, default=Path("logs/observe.json"), help="Log file path")
@click.option("--level", "-l", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), help="Filter by level")
@click.option("--follow", is_flag=True, help="Follow log output (like tail -f)")
@click.option("--lines", "-n", type=int, default=50, help="Number of lines to show")
def logs(log_file: Path, level: Optional[str], follow: bool, lines: int) -> None:
    """
    View structured logs.

    Example:
        observe observe logs
        observe observe logs --level ERROR
        observe observe logs --follow
        observe observe logs --lines 100
    """
    if not log_file.exists():
        console.print(f"[yellow]⚠[/yellow] Log file not found: {log_file}")
        return

    import json

    def read_logs() -> list:
        """Read and filter logs"""
        with open(log_file, "r") as f:
            all_lines = f.readlines()

        # Take last N lines
        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        logs_data = []
        for line in recent_lines:
            try:
                entry = json.loads(line)
                if level is None or entry.get("level") == level:
                    logs_data.append(entry)
            except json.JSONDecodeError:
                pass

        return logs_data

    def format_logs(logs_data: list) -> Table:
        """Format logs as table"""
        table = Table(title="Structured Logs", show_header=True)
        table.add_column("Time", style="dim")
        table.add_column("Level", style="bold")
        table.add_column("Message")

        for entry in logs_data:
            timestamp = entry.get("timestamp", "")[:19]  # Remove milliseconds
            log_level = entry.get("level", "INFO")
            message = entry.get("message", "")

            # Color code by level
            level_style = {
                "DEBUG": "[dim]DEBUG[/dim]",
                "INFO": "[cyan]INFO[/cyan]",
                "WARNING": "[yellow]WARNING[/yellow]",
                "ERROR": "[red]ERROR[/red]",
            }.get(log_level, log_level)

            table.add_row(timestamp, level_style, message)

        return table

    if follow:
        # Follow mode
        console.print("[dim]Following logs... (Ctrl+C to stop)[/dim]\n")

        last_size = 0

        try:
            with Live(console=console, refresh_per_second=1) as live:
                while True:
                    current_size = log_file.stat().st_size

                    if current_size > last_size:
                        logs_data = read_logs()
                        table = format_logs(logs_data)
                        live.update(table)
                        last_size = current_size

                    time.sleep(0.5)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped following logs[/dim]")
    else:
        # One-time display
        logs_data = read_logs()
        table = format_logs(logs_data)
        console.print(table)


@observe_.command()
@click.argument("trace_file", type=Path)
def trace(trace_file: Path) -> None:
    """
    Analyze trace file.

    Example:
        observe observe trace traces/trace_123.json
    """
    if not trace_file.exists():
        console.print(f"[red]✗[/red] Trace file not found: {trace_file}")
        raise SystemExit(1)

    import json

    with open(trace_file, "r") as f:
        data = json.load(f)

    trace_id = data.get("trace_id")
    spans = data.get("spans", [])

    console.print(f"[bold cyan]Trace ID:[/bold cyan] {trace_id}\n")

    # Spans table
    table = Table(title="Spans", show_header=True)
    table.add_column("Span Name", style="cyan")
    table.add_column("Duration (ms)", justify="right", style="green")
    table.add_column("Attributes", style="dim")

    for span in spans:
        name = span.get("name", "Unknown")
        duration = span.get("duration_ms", 0)
        attributes = span.get("attributes", {})

        attr_str = ", ".join(f"{k}={v}" for k, v in attributes.items())

        table.add_row(name, f"{duration:.2f}", attr_str)

    console.print(table)

    # Summary
    total_duration = sum(s.get("duration_ms", 0) for s in spans)
    console.print(f"\n[bold]Total Duration:[/bold] {total_duration:.2f}ms")
    console.print(f"[bold]Total Spans:[/bold] {len(spans)}")


@observe_.command()
def status() -> None:
    """
    Show observability status.

    Example:
        observe observe status
    """
    manager = ObservabilityManager.get_instance()

    # Metrics summary
    metrics_summary = manager.metrics.get_summary()

    table = Table(title="Observability Status", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="dim")

    table.add_row(
        "Metrics",
        "✓ Active",
        f"{metrics_summary['total_metrics']} metrics collected",
    )

    table.add_row(
        "Logging",
        "✓ Active",
        f"Log file: {manager.logger.log_path}",
    )

    if manager.tracing:
        table.add_row(
            "Tracing",
            "✓ Active",
            f"Trace ID: {manager.tracing.trace_id[:8]}...",
        )
    else:
        table.add_row(
            "Tracing",
            "○ Inactive",
            "No active trace",
        )

    console.print(table)


if __name__ == "__main__":
    observe_()
