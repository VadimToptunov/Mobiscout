"""``mobiscout events`` — query crawl sessions recorded with ``crawl
--record-events``.

The event database is written post-crawl (see ``storage.crawl_recorder``), so
these commands are pure readers over a SQLite file: list sessions, print a
session's timeline, or show aggregate statistics.
"""

from typing import Optional

import click
from rich.table import Table

from framework.cli.rich_output import print_error, print_header, print_info, console
from framework.storage.event_store import EventStore


def _default_session(store: EventStore) -> Optional[str]:
    """The most-recent session id, so single-session DBs need no --session."""
    sessions = store.get_sessions()
    return sessions[0]["session_id"] if sessions else None


def _summary(event: dict) -> str:
    """One-line description of an event row for the timeline."""
    data = event.get("data", {})
    if event["event_type"] == "navigation":
        return f"→ {data.get('toScreen', '?')}"
    if event["event_type"] == "ui":
        return f"tap {data.get('element', '?')}"
    return str(event["event_type"])


@click.group(name="events")
def events() -> None:
    """🗂️  Query crawl sessions recorded with `crawl --record-events`."""


@events.command()
@click.argument("db", type=click.Path(exists=True, dir_okay=False))
def sessions(db: str) -> None:
    """List the recorded sessions in an event database."""
    store = EventStore(db)
    rows = store.get_sessions()
    if not rows:
        print_info("No sessions recorded in this database.")
        return
    table = Table(title="Recorded sessions")
    table.add_column("Session", style="cyan")
    table.add_column("App")
    table.add_column("Device")
    table.add_column("Events", justify="right", style="green")
    for row in rows:
        table.add_row(
            row["session_id"],
            row.get("app_version") or "-",
            row.get("device_model") or "-",
            str(row.get("event_count", 0)),
        )
    console.print(table)


@events.command()
@click.argument("db", type=click.Path(exists=True, dir_okay=False))
@click.option("--session", "-s", default=None, help="Session id (default: the most recent).")
@click.option("--limit", default=200, show_default=True, help="Max events to print.")
def timeline(db: str, session: Optional[str], limit: int) -> None:
    """Print a session's event timeline (taps and navigations, in order)."""
    store = EventStore(db)
    sid = session or _default_session(store)
    if not sid:
        print_error("No sessions in this database.")
        raise click.Abort()

    print_header("Event timeline", sid)
    rows = store.get_events(session_id=sid, limit=limit)
    table = Table()
    table.add_column("#", justify="right", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Screen", overflow="fold")
    table.add_column("Event", style="green")
    for row in rows:
        table.add_row(str(row["timestamp"]), row["event_type"], str(row.get("screen") or "-"), _summary(row))
    console.print(table)


@events.command()
@click.argument("db", type=click.Path(exists=True, dir_okay=False))
@click.option("--session", "-s", default=None, help="Session id (default: all sessions).")
def stats(db: str, session: Optional[str]) -> None:
    """Show aggregate statistics for a database (or one session)."""
    store = EventStore(db)
    for key, value in store.get_statistics(session_id=session).items():
        print_info(f"{key}: {value}")
