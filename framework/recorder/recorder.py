"""
Live session recorder: manual taps on a device → a runnable test.

The pure core (:func:`tap_to_step`, :func:`steps_to_model`) resolves a tap to the
element under it and assembles a :class:`~framework.codegen.ir.TestModel`, reusing
the crawler's screen parser and locator ranking so recorded locators match the
quality of crawled ones. :class:`SessionRecorder` wraps that with the live
``adb getevent`` stream and hands the model to any codegen target.

Scope / honesty: taps are captured (the down position of each gesture); swipes
record as a tap at their origin, and **text input is not captured** — key events
are not reliably reconstructible from ``getevent`` across devices. Type steps are
best added by editing the generated test or via the parameterized crawl.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.codegen import get_emitter
from framework.codegen.ir import ActionType, Platform, Step, TestCase, TestModel
from framework.crawler.app_crawler import CrawlElement, parse_screen
from framework.crawler.to_codegen import selector_for
from framework.recorder.getevent import GeteventParser, Tap, find_touch_device


def _contains_point(element: CrawlElement, x: int, y: int) -> bool:
    """True if screen point ``(x, y)`` falls inside the element's bounds."""
    x1, y1, x2, y2 = element.bounds
    return x1 <= x <= x2 and y1 <= y <= y2


def _area(element: CrawlElement) -> int:
    """Bounding-box area — used to prefer the most specific (smallest) element."""
    x1, y1, x2, y2 = element.bounds
    return (x2 - x1) * (y2 - y1)


def tap_to_step(xml: str, x: int, y: int, platform: str = "android") -> Optional[Step]:
    """Resolve a tap at ``(x, y)`` on the given UI hierarchy to a TAP step.

    Picks the smallest element whose bounds contain the point and that yields a
    usable locator (so a tap on a labelled button beats a tap on its container),
    then builds a ranked, self-healing selector for it.

    Args:
        xml: the uiautomator / XCUITest page source at tap time.
        x: tap x in screen pixels.
        y: tap y in screen pixels.
        platform: "android" or "ios" (drives locator strategy).

    Returns:
        A :class:`Step` with ``TAP`` and a selector, or ``None`` if no element
        under the point produced a locator.
    """
    screen = parse_screen(xml)
    candidates = sorted((e for e in screen.elements if _contains_point(e, x, y)), key=_area)
    for element in candidates:
        selector = selector_for(element, screen.elements, platform)
        if selector is not None:
            return Step(action=ActionType.TAP, selector=selector, description=element.label)
    return None


def steps_to_model(
    package: str,
    steps: List[Step],
    platform: str = "android",
    name: str = "RecordedFlow",
    app_activity: Optional[str] = None,
) -> TestModel:
    """Wrap recorded steps in a single-case :class:`TestModel`, launch step first."""
    launch = Step(action=ActionType.LAUNCH, description=f"Launch {package}")
    case = TestCase(
        name="recorded_session",
        steps=[launch, *steps],
        description="Captured from a live recording session",
    )
    return TestModel(
        name=name,
        app_package=package,
        platform=Platform(platform),
        cases=[case],
        app_activity=app_activity,
    )


class SessionRecorder:
    """Records manual taps on an Android device and emits a test.

    Args:
        package: app under test (Android package).
        serial: adb serial of the target device, or ``None`` for the only device.
        platform: "android" (iOS live recording is not supported via getevent).
        adb: adb executable name/path.
    """

    def __init__(self, package: str, serial: Optional[str] = None, platform: str = "android", adb: str = "adb"):
        self.package = package
        self.serial = serial
        self.platform = platform
        self._adb = adb
        self.steps: List[Step] = []
        self.skipped = 0  # taps that resolved to no element

    def _cmd(self, *args: str) -> List[str]:
        """Build the adb argv, inserting ``-s <serial>`` when set."""
        base = [self._adb]
        if self.serial:
            base += ["-s", self.serial]
        return base + list(args)

    def _run(self, *args: str) -> str:
        """Run an adb command and return stdout."""
        return subprocess.run(self._cmd(*args), capture_output=True, text=True, timeout=15).stdout

    def _screen_size(self) -> tuple:
        """Read the device screen size in pixels via ``wm size`` (WxH)."""
        out = self._run("shell", "wm", "size")  # "Physical size: 1080x2340"
        for token in out.split():
            if "x" in token and token.replace("x", "").isdigit():
                w, h = token.split("x")
                return int(w), int(h)
        return 0, 0

    def _page_source(self) -> str:
        """Dump the current uiautomator hierarchy."""
        from framework.crawler.adb_driver import AdbCrawlerDriver

        return AdbCrawlerDriver(serial=self.serial, adb=self._adb).page_source()

    def _make_parser(self) -> tuple:
        """Probe the touchscreen + screen size; return (parser, device_path)."""
        device = find_touch_device(self._run("shell", "getevent", "-p"))
        if device is None:
            raise RuntimeError("No touchscreen input device found via 'getevent -p'")
        screen_w, screen_h = self._screen_size()
        parser = GeteventParser(device.max_x, device.max_y, screen_w, screen_h)
        return parser, device.path

    def _record_tap(self, tap: Tap) -> Optional[Step]:
        """Resolve a live tap to a step (dumping the hierarchy at tap time)."""
        step = tap_to_step(self._page_source(), tap.x, tap.y, self.platform)
        if step is None:
            self.skipped += 1
        else:
            self.steps.append(step)
        return step

    def record(self, on_step=None) -> None:
        """Stream ``getevent`` and capture taps until interrupted (blocking).

        Args:
            on_step: optional callback invoked with each resolved :class:`Step`
                (e.g. to print progress); ``None`` to record silently.
        """
        parser, device_path = self._make_parser()
        proc = subprocess.Popen(
            self._cmd("shell", "getevent", "-lt", device_path),
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                tap = parser.feed(line)
                if tap is not None:
                    step = self._record_tap(tap)
                    if step is not None and on_step is not None:
                        on_step(step)
        finally:
            proc.terminate()

    def emit(self, output: str, target: str = "python_pytest", app_activity: Optional[str] = None) -> Dict[str, Any]:
        """Build the model from recorded steps and write the test kit.

        Returns a summary dict; writes the raw model JSON plus the target's files
        under ``output``. Returns ``{"steps": 0}`` (writes nothing) if nothing was
        recorded.
        """
        out = Path(output)
        out.mkdir(parents=True, exist_ok=True)
        if not self.steps:
            return {"steps": 0, "target": target, "output": str(out.absolute()), "skipped": self.skipped}

        model = steps_to_model(self.package, self.steps, self.platform, app_activity=app_activity)
        for name, content in get_emitter(target).emit(model).items():
            path = out / target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")

        return {
            "steps": len(self.steps),
            "skipped": self.skipped,
            "target": target,
            "output": str(out.absolute()),
        }
