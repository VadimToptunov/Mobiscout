"""
CLI commands for API Mocking
"""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from framework.mocking import APIMocker

console = Console()


@click.group()
def mock():
    """API mocking and replay commands."""
    pass


@mock.command()
@click.argument("session_id")
@click.option("--appium-server", help="Appium server URL to proxy")
@click.option("--port", default=8888, help="Mock server port")
def record(session_id: str, appium_server: str, port: int):
    """Start recording API calls for a test session.

    Runs a forward HTTP proxy on ``--port``; point the app/emulator's HTTP proxy at
    it. Every request is forwarded to its real destination and the round-trip is
    saved into the session; HTTPS is tunnelled through un-recorded (see the note on
    stop). Press Ctrl+C to stop and persist.
    """
    from framework.mocking.proxy import MockProxy

    mocker = APIMocker()
    mocker.start_recording(session_id)
    proxy = MockProxy(mocker, port=port)

    console.print(
        Panel(
            f"[green]🔴 Recording API calls[/green]\n\n"
            f"Session ID: [cyan]{session_id}[/cyan]\n"
            f"Port: [cyan]{port}[/cyan]\n\n"
            f"[bold]Configure your app/emulator to use this HTTP proxy:[/bold]\n"
            f"http://localhost:{port}\n\n"
            f"[dim]HTTP API calls are recorded. HTTPS is passed through but not\n"
            f"recorded (needs TLS interception). Press Ctrl+C to stop.[/dim]",
            title="API Mock Recording",
            border_style="green",
        )
    )

    try:
        proxy.serve_forever()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Stopping recording...[/yellow]")
    finally:
        proxy.stop()

    stats = mocker.stop()
    if stats:
        https_note = (
            f"\n[yellow]HTTPS tunnels passed through un-recorded: {proxy.https_tunnels}[/yellow]"
            if proxy.https_tunnels
            else ""
        )
        console.print(
            Panel(
                f"[green]✅ Recording complete![/green]\n\n"
                f"Total requests: {stats['total_requests']}\n"
                f"Session saved: [cyan]{session_id}[/cyan]{https_note}\n\n"
                f"[dim]Use 'mobiscout mock replay {session_id}' to replay[/dim]",
                title="Recording Stats",
                border_style="green",
            )
        )


@mock.command()
@click.argument("session_id")
@click.option("--strict/--fuzzy", default=False, help="Strict matching (body + URL)")
@click.option("--port", default=8888, help="Mock server port")
def replay(session_id: str, strict: bool, port: int):
    """Replay recorded API calls.

    Runs the proxy in replay mode: recorded requests are answered from the session
    with no network call; an unrecorded request gets a ``504`` so the gap is
    visible. Point the app's HTTP proxy at ``--port`` and press Ctrl+C to stop.
    """
    from framework.mocking.proxy import MockProxy

    mocker = APIMocker()

    try:
        mocker.start_replay(session_id, strict=strict)
    except FileNotFoundError:
        console.print(f"[red]❌ Session '{session_id}' not found[/red]")
        console.print("\nAvailable sessions:")
        _list_sessions()
        return

    proxy = MockProxy(mocker, port=port)

    console.print(
        Panel(
            f"[green]▶️  Replaying API calls[/green]\n\n"
            f"Session ID: [cyan]{session_id}[/cyan]\n"
            f"Matching: [cyan]{'strict' if strict else 'fuzzy'}[/cyan]\n"
            f"Port: [cyan]{port}[/cyan]\n\n"
            f"[bold]Configure your app to use this proxy:[/bold]\n"
            f"http://localhost:{port}\n\n"
            f"[dim]API calls will be served from recorded mocks.\n"
            f"Press Ctrl+C to stop.[/dim]",
            title="API Mock Replay",
            border_style="blue",
        )
    )

    try:
        proxy.serve_forever()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Stopping replay...[/yellow]")
    finally:
        proxy.stop()

    stats = mocker.stop()
    if stats:
        console.print(
            Panel(
                f"[green]✅ Replay complete![/green]\n\n"
                f"Total requests: {stats['total_requests']}\n"
                f"Cache hits: {stats['cache_hits']}\n"
                f"Cache misses: {stats['cache_misses']}\n"
                f"Hit rate: {stats['hit_rate']}\n"
                f"Latency saved: {stats['latency_saved_ms']} ms\n\n"
                f"[dim]Session: {session_id}[/dim]",
                title="Replay Stats",
                border_style="blue",
            )
        )


@mock.command(name="list")
def list_command():
    """List all recorded mock sessions."""
    _list_sessions()


def _list_sessions():
    """Helper to list sessions"""
    mocker = APIMocker()
    sessions = mocker.list_sessions()

    if not sessions:
        console.print("[yellow]No mock sessions found[/yellow]")
        console.print("\nRecord your first session:")
        console.print("[cyan]mobiscout mock record my-session[/cyan]")
        return

    table = Table(title="Mock Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Created", style="dim")
    table.add_column("Mocks", justify="right")

    for session in sessions:
        table.add_row(session["session_id"], session["created_at"][:19], str(session["mock_count"]))

    console.print(table)


@mock.command()
@click.argument("session_id")
def inspect(session_id: str):
    """Inspect a mock session's contents."""

    try:
        from framework.mocking.storage import MockStorage

        storage = MockStorage()
        mocks = storage.load_session(session_id)
    except FileNotFoundError:
        console.print(f"[red]❌ Session '{session_id}' not found[/red]")
        return

    console.print(f"\n[bold]Session:[/bold] [cyan]{session_id}[/cyan]")
    console.print(f"[bold]Total mocks:[/bold] {len(mocks)}\n")

    for i, mock in enumerate(mocks, 1):
        console.print(
            Panel(
                f"[bold]{mock.request.method}[/bold] {mock.request.url}\n\n"
                f"[dim]Request Headers:[/dim]\n{_format_headers(mock.request.headers)}\n\n"
                f"[dim]Response:[/dim] {mock.response.status_code}\n"
                f"[dim]Latency:[/dim] {mock.response.latency_ms:.1f} ms\n"
                f"[dim]Used:[/dim] {mock.count} times",
                title=f"Mock #{i}",
                border_style="cyan",
            )
        )


def _format_headers(headers: dict) -> str:
    """Format headers for display"""
    return "\n".join([f"  {k}: {v}" for k, v in list(headers.items())[:3]])


@mock.command()
@click.argument("session_id")
@click.confirmation_option(prompt="Are you sure you want to delete this session?")
def delete(session_id: str):
    """Delete a mock session."""
    mocker = APIMocker()

    if mocker.delete_session(session_id):
        console.print(f"[green]✅ Deleted session '{session_id}'[/green]")
    else:
        console.print(f"[red]❌ Session '{session_id}' not found[/red]")


@mock.command()
@click.argument("session_id")
@click.option("--output", "-o", type=Path, required=True, help="Output file path")
def export(session_id: str, output: Path):
    """Export a mock session to a file."""
    mocker = APIMocker()

    try:
        mocker.export_session(session_id, output)
        console.print(f"[green]✅ Exported '{session_id}' to {output}[/green]")
    except FileNotFoundError:
        console.print(f"[red]❌ Session '{session_id}' not found[/red]")


@mock.command(name="import")
@click.argument("input_file", type=Path)
def import_command(input_file: Path):
    """Import a mock session from a file."""
    mocker = APIMocker()

    try:
        session_id = mocker.import_session(input_file)
        console.print(f"[green]✅ Imported session '{session_id}'[/green]")
    except Exception as e:
        console.print(f"[red]❌ Import failed: {e}[/red]")


@mock.command()
@click.argument("swagger_file", type=Path)
@click.argument("session_id")
def from_swagger(swagger_file: Path, session_id: str):
    """Generate mocks from Swagger/OpenAPI specification."""
    if not swagger_file.exists():
        console.print(f"[red]❌ File not found: {swagger_file}[/red]")
        return

    import json
    import yaml

    try:
        with open(swagger_file, "r") as f:
            if swagger_file.suffix in [".yaml", ".yml"]:
                spec = yaml.safe_load(f)
            else:
                spec = json.load(f)
    except Exception as e:
        console.print(f"[red]❌ Failed to parse Swagger file: {e}[/red]")
        return

    mocker = APIMocker()

    with console.status("[cyan]Generating mocks from Swagger spec..."):
        count = mocker.generate_from_swagger(spec, session_id)

    console.print(
        Panel(
            f"[green]✅ Generated {count} mocks![/green]\n\n"
            f"Session ID: [cyan]{session_id}[/cyan]\n\n"
            f"[dim]Use 'mobiscout mock replay {session_id}' to test[/dim]",
            title="Swagger Import",
            border_style="green",
        )
    )


@mock.command()
@click.argument("session_id")
@click.argument("old_url")
@click.argument("new_url")
def rewrite_urls(session_id: str, old_url: str, new_url: str):
    """Rewrite URLs in a mock session (e.g., change base URL)."""
    from framework.mocking.storage import MockStorage

    storage = MockStorage()

    try:
        mocks = storage.load_session(session_id)
    except FileNotFoundError:
        console.print(f"[red]❌ Session '{session_id}' not found[/red]")
        return

    count = 0
    for mock in mocks:
        if mock.request.url.startswith(old_url):
            mock.request.url = mock.request.url.replace(old_url, new_url, 1)
            count += 1

    storage.save_session(session_id, mocks)

    console.print(f"[green]✅ Rewrote {count} URLs in session '{session_id}'[/green]")


if __name__ == "__main__":
    mock()
