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
# Same line, but keeping the activity half too — what a generated kit needs for appActivity.
_RESUMED_COMPONENT_RE = re.compile(
    r"(?:topResumedActivity|ResumedActivity:|mResumedActivity)[^\n]*?\s([\w.]+)/([\w.$]+)"
)
_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s([\w.]+)/[\w.$]+\}")

# `dumpsys window displays` reports the display's CURRENT size as `cur=WxH` (it
# follows rotation), while `wm size` — the fallback — reports the device's natural,
# portrait size.
_DISPLAY_CUR_RE = re.compile(r"\bcur=(\d+)x(\d+)")
_WM_SIZE_RE = re.compile(r"\b(\d+)x(\d+)\b")

# Where the fallback dump is written. The conventional path every adb-based tool
# uses, so anything left there may well be someone else's (stale) dump.
_DUMP_FILE = "/sdcard/window_dump.xml"


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


def _encode_text(text: str) -> str:
    """Encode ``text`` for ``adb shell input text``. Two hazards, two layers:

    1. ``input text`` maps ``%s`` to a space, so spaces are encoded as ``%s``.
    2. adb concatenates its ``shell`` argv into a command line that the DEVICE
       shell re-parses, so ``&``, ``;``, ``$``, backticks, quotes are interpreted
       rather than typed — a waypoint password like ``S&p500`` types "S" and hands
       the rest to the shell, and the gate never opens. Wrapping the whole token in
       single quotes (embedded quote escaped as ``'\\''``) makes it all literal.

    Mirrors ``JSONRPCServer._encode_adb_text``, which solves the same problem for
    the recorder's taps; the two should share one helper.
    """
    return "'" + text.replace(" ", "%s").replace("'", "'\\''") + "'"


class AdbCrawlerDriver:
    """CrawlerDriver implemented with adb shell commands."""

    def __init__(
        self,
        serial: Optional[str] = None,
        adb: str = "adb",
        settle: float = 0.8,
        timeout: float = 60.0,
        retries: int = 2,
        launch_args: Optional[List[str]] = None,
    ) -> None:
        self._adb = adb
        self._serial = serial
        self._settle_max = settle
        self._timeout = timeout
        self._retries = max(0, retries)  # extra attempts after the first
        # Extra `am start` tokens (intent extras) appended on every launch, e.g.
        # ["--es", "APP_START_UNLOCKED", "true"] to skip an auth gate. Threaded so
        # the crawler's own recovery relaunches keep the same start state.
        self._launch_args = list(launch_args or [])
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

        A command adb or the device *rejected* ("more than one device/emulator",
        "device offline", an input the device refused) raises the same error rather
        than returning its empty stdout: served as an empty dump it would read as
        "the app has no screens", and the whole broken-device run would be reported
        as a successful crawl of nothing. Only a non-zero exit that also wrote to
        stderr counts — an on-device ``grep`` that simply found no match exits 1
        silently and is a normal result. Calls that report failure themselves go
        through :meth:`_try_run`.

        Args:
            *args: adb arguments (after any ``-s <serial>``), e.g. ``"shell",
                "input", "tap", "10", "20"``.

        Returns:
            The command's stdout as text.

        Raises:
            CrawlerDriverError: the command timed out on every attempt, or adb /
                the device rejected it.
        """
        last: Optional[subprocess.TimeoutExpired] = None
        for attempt in range(self._retries + 1):
            try:
                # text=True alone decodes with the locale codepage (cp125x on
                # Windows); uiautomator dumps are UTF-8, so any Cyrillic/CJK app
                # text would raise UnicodeDecodeError and kill the crawl.
                proc = subprocess.run(
                    self._cmd(*args),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self._timeout,
                )
            except subprocess.TimeoutExpired as exc:
                last = exc
                if attempt < self._retries:
                    time.sleep(0.5)  # let the device settle before retrying
                continue
            err = (proc.stderr or "").strip()
            if proc.returncode != 0 and err:
                raise CrawlerDriverError(f"adb {' '.join(args[:2])} failed: {err}")
            return proc.stdout
        raise CrawlerDriverError(
            f"adb command timed out after {self._retries + 1} attempt(s): {' '.join(args)}"
        ) from last

    def _try_run(self, *args: str) -> str:
        """Run an adb command whose failure the caller judges for itself — a dump we
        validate before serving, a launch we confirm by polling the foreground —
        returning "" instead of ending the crawl on it."""
        try:
            return self._run(*args)
        except CrawlerDriverError:
            return ""

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
        # Delete the file first and validate what comes back, because the usual
        # reason a dump fails is transient (uiautomator's "could not get idle
        # state." on a busy screen) and a failed dump leaves the PREVIOUS one in
        # place: cat would then serve a screen that is no longer displayed, and the
        # crawler would fingerprint it and tap coordinates read off it. An empty
        # read is the honest answer — the next dump gets the real screen.
        self._try_run("shell", "rm", "-f", _DUMP_FILE)
        self._try_run("shell", "uiautomator", "dump", _DUMP_FILE)
        return _extract_hierarchy(self._try_run("shell", "cat", _DUMP_FILE)) or ""

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

        The text is encoded for the device shell (see :func:`_encode_text`) so
        waypoint values with shell metacharacters — passwords, sample data — are
        typed as written instead of being re-parsed as commands.
        """
        self._run("shell", "input", "text", _encode_text(text))
        self._settle_wait()

    def clear_field(self) -> None:
        """Clear the focused field so a re-fill replaces rather than appends.

        adb has no element handle, so move the cursor to the end of the text and
        send a bounded run of deletes. ``input keyevent`` takes several keycodes in
        one call, so this is two adb round-trips: 123 = MOVE_END, then 67 = DEL x64
        (enough for realistic form fields, without an unbounded loop on a field we
        can't measure).
        """
        self._run("shell", "input", "keyevent", "123")
        self._run("shell", "input", "keyevent", *(["67"] * 64))
        self._settle_wait()

    def back(self) -> None:
        """Press the hardware/system Back key and wait for the UI to settle."""
        self._run("shell", "input", "keyevent", "4")
        self._settle_wait()

    def _screen_size(self) -> Tuple[int, int]:
        """Screen size in pixels for the CURRENT orientation, or (0, 0) if unknown.

        Read fresh (rotation changes mid-crawl) and from `dumpsys window displays`
        rather than `wm size`, which always reports the device's *natural* portrait
        size — on a landscape screen that would put a gesture off-display.
        """
        m = _DISPLAY_CUR_RE.search(self._try_run("shell", "dumpsys window displays | grep -E 'cur='"))
        if m:
            return int(m.group(1)), int(m.group(2))
        # Fallback: "Physical size: 1080x2340" plus, when one is set, an "Override
        # size:" line that supersedes it — so take the last match.
        sizes = _WM_SIZE_RE.findall(self._try_run("shell", "wm", "size"))
        return (int(sizes[-1][0]), int(sizes[-1][1])) if sizes else (0, 0)

    def scroll(self, direction: str = "down") -> None:
        """Swipe to reveal off-screen content, then wait for the UI to settle.

        ``down`` scrolls the content up (swipe from lower to upper) so below-the-
        fold rows and links come into view; any other value scrolls back up. The
        gesture is derived from the device's real screen size: the old fixed
        1080x1920-relative swipe started at y=1500, which is off-display on a
        720x1280 phone and on *any* device in landscape — Android drops a motion
        event that starts outside the display, so the scroll was a silent no-op and
        everything below the fold went uncrawled.
        """
        w, h = self._screen_size()
        if w <= 0 or h <= 0:
            return  # unknown geometry — a blind swipe would likely be dropped anyway
        x, lo, hi = w // 2, int(h * 0.75), int(h * 0.25)
        from_y, to_y = (lo, hi) if direction == "down" else (hi, lo)
        self._run("shell", "input", "swipe", str(x), str(from_y), str(x), str(to_y), "300")
        self._settle_wait()

    def hide_keyboard(self) -> None:
        """Dismiss the soft keyboard after form-filling, so it doesn't cover the
        control the crawler taps next (submit sits under the IME on most forms).

        Back is what dismisses an IME on Android — but Back with no IME up
        *navigates*, silently moving the crawl off the screen it is working on — so
        the keyevent is only sent when the IME is actually showing.
        """
        shown = self._try_run("shell", "dumpsys input_method | grep -E 'mInputShown'")
        if "mInputShown=true" not in shown:
            return
        self._run("shell", "input", "keyevent", "4")
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

    def current_activity(self, package: str) -> str:
        """The activity of ``package`` currently in the foreground, or "".

        Returned fully qualified (``it.feio.android.omninotes.MainActivity``), which is what
        a generated kit needs for ``appActivity``. Without it Appium resolves the launcher
        itself, and for an app declaring several launcher entries that resolution returns
        Android's chooser (``com.android.internal.app.ResolverActivity``) — which is not
        launchable, so every test errors out before it starts. Reading the activity the
        crawl actually ran sidesteps the ambiguity entirely.
        """
        dump = self._run("shell", "dumpsys activity activities | grep -E 'ResumedActivity'")
        for match in _RESUMED_COMPONENT_RE.finditer(dump):
            if match.group(1) != package:
                continue
            activity = match.group(2)
            # dumpsys abbreviates an activity in the package's own namespace as ".Name".
            return f"{package}{activity}" if activity.startswith(".") else activity
        return ""

    # Launcher activities that belong to a bundled diagnostic tool rather than the app.
    # A debug build routinely ships one (LeakCanary adds its own launcher icon), which is
    # what makes `resolve-activity` ambiguous in the first place.
    _NON_APP_LAUNCHERS = ("leakcanary.", "com.squareup.leakcanary")

    def _launcher_activities(self, package: str) -> List[str]:
        """The app's own launcher activities as ``package/activity``, best first.

        Used when ``resolve-activity`` answers with Android's chooser, which it does
        whenever a package declares more than one launcher entry. Falling back to `monkey`
        there is not safe: monkey picks one of them, and on a debug build that is as likely
        to be LeakCanary's launcher as the app's — the crawl would then faithfully explore
        the leak viewer instead of the app under test.

        Returns every candidate rather than one, because an app that ships alternative icons
        declares them as activity-aliases and disables all but the current one (Wikipedia
        does exactly this); a disabled alias is listed but refuses to start, so the caller
        tries them in turn.
        """
        dump = self._try_run("shell", f"dumpsys package {package} | grep -B4 android.intent.category.LAUNCHER")
        found = re.findall(rf"{re.escape(package)}/[A-Za-z0-9_.$]+", dump)
        return [
            component
            for component in dict.fromkeys(found)  # keep discovery order, drop duplicates
            if not any(component.split("/", 1)[1].startswith(p) for p in self._NON_APP_LAUNCHERS)
        ]

    def launch(self, package: str, tries: int = 8) -> bool:
        """Bring ``package`` to the foreground and wait until it's actually there.

        Resolves the app's launchable activity and starts it explicitly — ``monkey
        -c LAUNCHER`` silently fails to foreground some apps (a splash activity,
        an odd intent filter), which then reads as "not in the foreground" and
        aborts the crawl. Falls back to monkey. Polls until the app is resumed or
        we give up, so a slow cold start doesn't look like a failure.

        Returns whether the app reached the foreground.
        """
        # The three launch commands tolerate failure: a package that won't resolve or
        # an intent the device refuses is reported by the foreground poll below (this
        # returns a bool), not by raising out of the caller's recovery path.
        activity = ""
        resolved = self._try_run(
            "shell", "cmd", "package", "resolve-activity", "--brief", "-c", "android.intent.category.LAUNCHER", package
        )
        for line in resolved.strip().splitlines():
            if "/" in line and package in line:
                activity = line.strip()
        candidates = [activity] if activity else self._launcher_activities(package)
        started = False
        for candidate in candidates:
            self._try_run("shell", "am", "start", "-n", candidate, *self._launch_args)
            if self._foreground_within(package, tries=3):
                started = True
                break
        if not started and not candidates:
            # monkey can't carry intent extras; without a resolvable activity the
            # launch args are lost, but this path is a rare fallback.
            self._try_run("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
        return started or self._foreground_within(package, tries)

    def _foreground_within(self, package: str, tries: int) -> bool:
        """Poll until ``package`` is the foreground app, so a slow cold start isn't a failure."""
        for _ in range(tries):
            if self.current_package() == package:
                return True
            time.sleep(1.0)  # let a splash reach the real activity
        return self.current_package() == package

    def open_url(self, uri: str, package: Optional[str] = None, tries: int = 6) -> bool:
        """Open a deeplink URI (implicit VIEW intent) so a seed crawl starts on the
        target screen. When ``package`` is given, confirm the app under test — not a
        browser or another handler — actually came to the foreground; returns that.
        """
        # A URI no app handles is a "no" for this seed (the poll below), not a
        # crawl-ending device failure — so tolerate the intent being refused.
        self._try_run("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", uri)
        if package is None:
            return True
        for _ in range(tries):
            if self.current_package() == package:
                return True
            time.sleep(0.8)
        return self.current_package() == package
