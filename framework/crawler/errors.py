"""Crawler driver error type.

Drivers (adb, Appium) talk to a live device over flaky I/O: adb round-trips and
Appium calls hang or fail intermittently (a busy ``uiautomator`` service, a
momentary socket stall, a device mid-animation). A driver raises
``CrawlerDriverError`` for a transient failure that outlived its own retries, so
the crawl loop can end gracefully — keeping the screens gathered so far — instead
of crashing and losing the whole run to a single hiccup.
"""

from __future__ import annotations


class CrawlerDriverError(RuntimeError):
    """A driver command failed to reach the device after exhausting its retries.

    Raised by concrete drivers (e.g. :class:`AdbCrawlerDriver`) so callers can
    distinguish a transient device/transport failure from a programming error and
    degrade gracefully rather than propagate a raw ``subprocess.TimeoutExpired``.
    """
