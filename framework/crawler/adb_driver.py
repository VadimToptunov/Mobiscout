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

from framework.crawler.errors import CrawlerDriverError
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

    def __init__(
        self,
        serial: Optional[str] = None,
        adb: str = "adb",
        settle: float = 0.8,
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        self._adb = adb
        self._serial = serial
        self._settle_max = settle
        self._timeout = timeout
        self._retries = max(0, retries)  # extra attempts after the first
        self._cache: Optional[Tuple[float, str]] = None  # (monotonic ts, source)

    def _cmd(self, *args: str) -> List[str]:
        """Build the full adb argv, inserting ``-s <serial>`` when a serial is set."""
        base = [self._adb]
        if self._serial:
            base += ["-s", self._serial]
        return base + list(args)

    def _run(self, *args: str) -> str:
        """Run an adb command and return its stdout.

        adb round-trips hang intermittently on real devices and emulators — a busy
        ``uiautomator`` service, a device mid-animation, a momentary socket stall.
        A single hiccup must not abort a whole crawl, so a timed-out command is
        retried up to ``retries`` times (with a short pause to let the device
        recover). Only a timeout that outlives every attempt raises
        :class:`CrawlerDriverError`, which the crawl loop catches to finish
        gracefully with the screens gathered so far.

        Args:
            *args: adb arguments (after any ``-s <serial>``), e.g. ``"shell",
                "input", "tap", "10", "20"``.

        Returns:
            The command's stdout as text.

        Raises:
            CrawlerDriverError: the command timed out on every attempt.
        """
        last: Optional[subprocess.TimeoutExpired] = None
        for attempt in range(self._retries + 1):
            try:
                proc = subprocess.run(self._cmd(*args), capture_output=True, text=True, timeout=self._timeout)
                return proc.stdout
            except subprocess.TimeoutExpired as exc:
                last = exc
                if attempt < self._retries:
                    time.sleep(0.5)  # let the device settle before retrying
        raise CrawlerDriverError(
            f"adb command timed out after {self._retries + 1} attempt(s): {' '.join(args)}"
        ) from last

    def _dump(self) -> str:
        """Capture the current UI hierarchy as XML in one adb round-trip.

        ``uiautomator dump /dev/tty`` streams the XML straight to stdout, so we
        skip the separate file write + ``cat`` read; ``exec-out`` avoids the
        shell's CRLF mangling. Falls back to dump-to-file then read-back for
        devices that won't stream to ``/dev/tty``.
        """
        xml = _extract_hierarchy(self._run("exec-out", "uiautomator", "dump", "/dev/tty"))
        if xml is not None:
            return xml
        # Fallback for devices that won't stream to /dev/tty: file then read back.
        self._run("shell", "uiautomator", "dump", "/sdcard/window_dump.xml")
        return self._run("shell", "cat", "/sdcard/window_dump.xml")

    def page_source(self) -> str:
        """Return the current screen's UI-tree XML (CrawlerDriver protocol).

        Serves the dump captured while settling (still fresh, <1s old) to avoid a
        second, costly ``uiautomator dump`` right after a tap; otherwise dumps now.
        """
        if self._cache and (time.monotonic() - self._cache[0]) < 1.0:
            source = self._cache[1]
            self._cache = None
            return source
        return self._dump()

    def refresh(self, wait: float = 1.0) -> str:
        """A second, longer look for screens whose content loads asynchronously
        (RecyclerView population, network fetch). Those settle "stable but empty"
        on the first read; waiting a beat and re-dumping catches the real content.
        """
        time.sleep(wait)
        self._cache = None
        return self._dump()

    def _settle_wait(self) -> None:
        """Block until the UI stops animating (or the settle cap elapses),
        caching the final dump so the next ``page_source`` is free."""
        settle_until_stable(self._dump, self._remember, max_wait=self._settle_max)

    def _remember(self, source: str) -> None:
        """Cache a dump with its capture time so ``page_source`` can reuse it."""
        self._cache = (time.monotonic(), source)

    def tap(self, x: int, y: int) -> None:
        """Tap the screen at ``(x, y)`` and wait for the UI to settle."""
        self._run("shell", "input", "tap", str(x), str(y))
        self._settle_wait()

    def type_text(self, text: str) -> None:
        """Type ``text`` into the focused field and wait for the UI to settle.

        ``adb shell input text`` needs spaces as ``%s``; good enough for waypoint
        form-filling (emails, sample data, OTP codes).
        """
        self._run("shell", "input", "text", text.replace(" ", "%s"))
        self._settle_wait()

    def back(self) -> None:
        """Press the hardware/system Back key and wait for the UI to settle."""
        self._run("shell", "input", "keyevent", "4")
        self._settle_wait()

    def scroll(self, direction: str = "down") -> None:
        """Swipe to reveal off-screen content, then wait for the UI to settle.

        ``down`` scrolls the content up (swipe from lower to upper) so below-the-
        fold rows and links come into view; any other value scrolls back up. Uses
        a fixed 1080x1920-relative gesture — coarse but device-agnostic enough for
        exploration.
        """
        x, lo, hi = 540, 1500, 500
        from_y, to_y = (lo, hi) if direction == "down" else (hi, lo)
        self._run("shell", "input", "swipe", str(x), str(from_y), str(x), str(to_y), "300")
        self._settle_wait()

    def current_package(self) -> str:
        """Return the package of the app currently in the foreground ("" if none).

        Prefers the resumed activity (the app actually focused), falling back to
        ``mCurrentFocus`` while ignoring ANR / system windows.
        """
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

    def launch(self, package: str, tries: int = 8) -> bool:
        """Bring ``package`` to the foreground and wait until it's actually there.

        Resolves the app's launchable activity and starts it explicitly — ``monkey
        -c LAUNCHER`` silently fails to foreground some apps (a splash activity,
        an odd intent filter), which then reads as "not in the foreground" and
        aborts the crawl. Falls back to monkey. Polls until the app is resumed or
        we give up, so a slow cold start doesn't look like a failure.

        Returns whether the app reached the foreground.
        """
        activity = ""
        resolved = self._run(
            "shell", "cmd", "package", "resolve-activity", "--brief", "-c", "android.intent.category.LAUNCHER", package
        )
        for line in resolved.strip().splitlines():
            if "/" in line and package in line:
                activity = line.strip()
        if activity:
            self._run("shell", "am", "start", "-n", activity)
        else:
            self._run("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
        for _ in range(tries):
            if self.current_package() == package:
                return True
            time.sleep(1.0)  # let a splash reach the real activity
        return self.current_package() == package
