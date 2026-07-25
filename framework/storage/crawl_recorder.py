"""Persist a completed crawl as a queryable event session in the EventStore.

Zero crawl-hot-path overhead **by design**: events are *derived from the finished
``CrawlResult``* — taps become UI events, transitions become navigation events —
so recording is opt-in (``crawl --record-events``) and never touches the crawl
loop or its latency. Query the result with ``mobiscout events``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Union

from framework.storage.event_store import EventStore

if TYPE_CHECKING:
    from framework.crawler.models import CrawlElement, CrawlResult


def _element_label(element: "CrawlElement") -> str:
    """A human-ish label for a tapped element, from the most identifying field."""
    return element.text or element.content_desc or element.resource_id or element.class_name or "element"


def record_crawl_session(
    result: "CrawlResult",
    db_path: Union[str, Path],
    session_id: str,
    package: str = "",
    platform: str = "android",
) -> int:
    """Write a crawl's taps and transitions to the EventStore as one session.

    Each transition yields two ordered events — a ``ui`` tap on the source screen
    and a ``navigation`` from the source to the destination screen. Timestamps are
    a synthetic monotonic sequence (the crawl does not wall-clock its steps); order
    is what the timeline needs.

    Args:
        result: the finished crawl.
        db_path: SQLite file to write (created if absent).
        session_id: identifier for this crawl session.
        package: app under test, stored as session app metadata.
        platform: android/ios, stored as session device metadata.

    Returns:
        The number of events written.
    """
    store = EventStore(str(db_path))
    meta = {"deviceModel": platform, "appVersion": package}
    written = 0
    timestamp = 0
    for from_fp, element, to_fp in result.transitions:
        store.add_event(
            {
                "sessionId": session_id,
                "timestamp": timestamp,
                "actionType": "tap",
                "screen": from_fp,
                "element": _element_label(element),
                **meta,
            }
        )
        store.add_event(
            {
                "sessionId": session_id,
                "timestamp": timestamp + 1,
                "navType": "transition",
                "fromScreen": from_fp,
                "toScreen": to_fp,
                **meta,
            }
        )
        timestamp += 2
        written += 2
    return written
