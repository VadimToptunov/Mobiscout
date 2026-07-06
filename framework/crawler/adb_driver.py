"""
adb-backed CrawlerDriver — drive the crawler with plain adb, no Appium.

Uses `uiautomator dump` for the UI tree, `input tap` / `input keyevent` for
gestures, and `dumpsys window` for the foreground package. Handy for CI/local
runs against an emulator without an Appium server.
"""

from __future__ import annotations

import re
import subprocess
import time
from typing import List, Optional, Tuple

from framework.crawler.settle import settle_until_stable

# The foreground app is the RESUMED activity. mCurrentFocus is unreliable — it
# points at dialogs / ANR ("Application Not Responding: ...") / system windows.
_RESUMED_RE = re.compile(r"(?:topResumedActivity|ResumedActivity:|mResumedActivity)[^\n]*?\s([\w.]+)/[\w.$]+")
_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s([\w.]+)/[\w.$]+\}")


def _extract_hierarchy(raw: str) -> Optional[str]:
    """From `uiautomator dump /dev/tty` stdout, return the XML up to the closing
    </hierarchy> tag (dropping the trailing "UI hierarchy dumped..." line), or
    None if the stream didn't contain a hierarchy (caller falls back)."""
    end = raw.rfind("</hierarchy>")
    if end == -1:
        return None
    start = raw.find("<?xml")
    start = start if start != -1 else raw.find("<hierarchy")
    return raw[start if start != -1 else 0 : end + len("</hierarchy>")]


class AdbCrawlerDriver:
    """CrawlerDriver implemented with adb shell commands."""

    def __init__(self, serial: Optional[str] = None, adb: str = "adb", settle: float = 0.8):
        self._adb = adb
        self._serial = serial
        self._settle_max = settle
        self._cache: Optional[Tuple[float, str]] = None  # (monotonic ts, source)

    def _cmd(self, *args: str) -> List[str]:
        base = [self._adb]
        if self._serial:
            base += ["-s", self._serial]
        return base + list(args)

    def _run(self, *args: str) -> str:
        proc = subprocess.run(self._cmd(*args), capture_output=True, text=True, timeout=60)
        return proc.stdout

    def _dump(self) -> str:
        # One adb round-trip: `uiautomator dump /dev/tty` streams the XML straight
        # to stdout, so we skip the separate file write + `cat` read. exec-out
        # avoids the shell's CRLF mangling.
        xml = _extract_hierarchy(self._run("exec-out", "uiautomator", "dump", "/dev/tty"))
        if xml is not None:
            return xml
        # Fallback for devices that won't stream to /dev/tty: file then read back.
        self._run("shell", "uiautomator", "dump", "/sdcard/window_dump.xml")
        return self._run("shell", "cat", "/sdcard/window_dump.xml")

    def page_source(self) -> str:
        # Serve the dump captured while settling (fresh) to avoid a second, costly
        # uiautomator dump right after a tap.
        if self._cache and (time.monotonic() - self._cache[0]) < 1.0:
            source = self._cache[1]
            self._cache = None
            return source
        return self._dump()

    def _settle_wait(self) -> None:
        settle_until_stable(self._dump, self._remember, max_wait=self._settle_max)

    def _remember(self, source: str) -> None:
        self._cache = (time.monotonic(), source)

    def tap(self, x: int, y: int) -> None:
        self._run("shell", "input", "tap", str(x), str(y))
        self._settle_wait()

    def back(self) -> None:
        self._run("shell", "input", "keyevent", "4")
        self._settle_wait()

    def current_package(self) -> str:
        # Prefer the resumed activity (the app actually in the foreground). grep
        # on-device so adb transfers only the matching line(s), not the whole
        # multi-KB activity dump — this runs 2x per crawl step.
        m = _RESUMED_RE.search(self._run("shell", "dumpsys activity activities | grep -E 'ResumedActivity'"))
        if m:
            return m.group(1)
        # Fallback: mCurrentFocus, ignoring ANR / system windows.
        for line in self._run("shell", "dumpsys", "window").splitlines():
            if "mCurrentFocus" in line and "Not Responding" not in line:
                fm = _FOCUS_RE.search(line)
                if fm:
                    return fm.group(1)
        return ""
