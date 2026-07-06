"""
Adaptive settle — wait for the UI to stop changing instead of a fixed sleep.

After a tap/back the screen animates for a while, then stabilises. A fixed
``sleep(0.8)`` pays the worst case every time, even though most screens settle in
100-200 ms. This polls the UI and returns as soon as two consecutive snapshots
match (stable), capped at ``max_wait`` so it is never slower than the old sleep.

The final snapshot is handed back so the caller can cache it — the crawler asks
for ``page_source()`` right after settling, and serving the cached dump avoids a
second, redundant (and on adb, expensive) UI dump.
"""

from __future__ import annotations

import hashlib
import time
from typing import Callable, Optional


def _digest(source: str) -> str:
    return hashlib.md5(source.encode("utf-8", "ignore")).hexdigest() if source else ""


def settle_until_stable(
    snapshot: Callable[[], str],
    on_snapshot: Optional[Callable[[str], None]] = None,
    *,
    min_wait: float = 0.05,
    poll: float = 0.1,
    max_wait: float = 0.8,
) -> str:
    """Poll ``snapshot()`` until the UI is stable (two identical dumps) or
    ``max_wait`` elapses; return the final snapshot.

    ``on_snapshot`` is invoked with every dump so a driver can cache the freshest
    one. An empty/failed dump never counts as stable, so a flaky device just falls
    back to waiting up to ``max_wait`` — same as the old fixed sleep.
    """
    time.sleep(min_wait)  # let the transition begin before the first look
    deadline = time.monotonic() + max_wait
    last = None
    while True:
        source = snapshot()
        if on_snapshot is not None:
            on_snapshot(source)
        digest = _digest(source)
        if digest and digest == last:
            return source  # settled
        last = digest
        if time.monotonic() >= deadline:
            return source  # capped — no slower than the old sleep
        time.sleep(poll)
