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
from typing import List, Optional

_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s([\w.]+)/[\w.]+")
_FOCUS_RE_ALT = re.compile(r"mResumedActivity[^{]*\{[^ ]*\s([\w.]+)/")


class AdbCrawlerDriver:
    """CrawlerDriver implemented with adb shell commands."""

    def __init__(self, serial: Optional[str] = None, adb: str = "adb", settle: float = 0.8):
        self._adb = adb
        self._serial = serial
        self._settle = settle

    def _cmd(self, *args: str) -> List[str]:
        base = [self._adb]
        if self._serial:
            base += ["-s", self._serial]
        return base + list(args)

    def _run(self, *args: str) -> str:
        proc = subprocess.run(self._cmd(*args), capture_output=True, text=True, timeout=60)
        return proc.stdout

    def page_source(self) -> str:
        # Dump to the device then read it back (uiautomator dump prints only a path).
        self._run("shell", "uiautomator", "dump", "/sdcard/window_dump.xml")
        return self._run("shell", "cat", "/sdcard/window_dump.xml")

    def tap(self, x: int, y: int) -> None:
        self._run("shell", "input", "tap", str(x), str(y))
        time.sleep(self._settle)

    def back(self) -> None:
        self._run("shell", "input", "keyevent", "4")
        time.sleep(self._settle)

    def current_package(self) -> str:
        out = self._run("shell", "dumpsys", "window")
        m = _FOCUS_RE.search(out)
        if m:
            return m.group(1)
        out = self._run("shell", "dumpsys", "activity", "activities")
        m = _FOCUS_RE_ALT.search(out)
        return m.group(1) if m else ""
