"""
Streaming parser for ``adb shell getevent -lt`` touch output.

``getevent -l`` prints one input event per line with symbolic type/code names but
**hex values**, e.g.::

    [   106.740] /dev/input/event1: EV_ABS  ABS_MT_TRACKING_ID  0000000b
    [   106.740] /dev/input/event1: EV_ABS  ABS_MT_POSITION_X   000001f4
    [   106.740] /dev/input/event1: EV_ABS  ABS_MT_POSITION_Y   00000384
    [   106.740] /dev/input/event1: EV_KEY  BTN_TOUCH           DOWN
    ...
    [   106.820] /dev/input/event1: EV_ABS  ABS_MT_TRACKING_ID  ffffffff
    [   106.820] /dev/input/event1: EV_KEY  BTN_TOUCH           UP

A *tap* is a touch-down followed by a touch-up. The finger's coordinates arrive in
touch-panel units, which on many devices differ from screen pixels, so they are
scaled by ``screen / touch_max``. The gesture's **down** position is taken as the
tap point (so a swipe records as a tap at its origin — a documented v1 limitation).

The parser is deliberately pure and line-at-a-time (:meth:`GeteventParser.feed`)
so it can sit on a live subprocess stream *and* be unit-tested against canned
output with no device.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# "EV_ABS  ABS_MT_POSITION_X  000001f4" — capture the code and the hex value.
_LINE = re.compile(r"(ABS_MT_POSITION_X|ABS_MT_POSITION_Y|ABS_MT_TRACKING_ID|BTN_TOUCH)\s+([0-9a-fA-F]+|UP|DOWN)")
_TRACKING_UP = "ffffffff"  # ABS_MT_TRACKING_ID value that ends a touch


@dataclass(frozen=True)
class Tap:
    """A completed tap in **screen pixel** coordinates."""

    x: int
    y: int


class GeteventParser:
    """Turns a stream of ``getevent -l`` lines into :class:`Tap` s.

    Args:
        touch_max_x: max raw ``ABS_MT_POSITION_X`` the panel reports (from
            ``getevent -p``); ``0`` means the raw values are already in pixels.
        touch_max_y: max raw ``ABS_MT_POSITION_Y``; ``0`` for identity scaling.
        screen_w: device screen width in pixels (from ``wm size``).
        screen_h: device screen height in pixels.
    """

    def __init__(self, touch_max_x: int, touch_max_y: int, screen_w: int, screen_h: int) -> None:
        self._max_x = touch_max_x
        self._max_y = touch_max_y
        self._w = screen_w
        self._h = screen_h
        self._down = False  # inside a touch (between down and up)
        self._raw_x: Optional[int] = None
        self._raw_y: Optional[int] = None
        self._captured = False  # have we locked the tap's origin coords?
        self._tap_x = 0
        self._tap_y = 0

    def _scale_x(self, raw: int) -> int:
        return round(raw * self._w / self._max_x) if self._max_x else raw

    def _scale_y(self, raw: int) -> int:
        return round(raw * self._h / self._max_y) if self._max_y else raw

    def feed(self, line: str) -> Optional[Tap]:
        """Consume one line; return a :class:`Tap` when a touch-up completes it."""
        m = _LINE.search(line)
        if not m:
            return None
        code, value = m.group(1), m.group(2)

        if code == "ABS_MT_POSITION_X":
            self._raw_x = int(value, 16)
        elif code == "ABS_MT_POSITION_Y":
            self._raw_y = int(value, 16)
        elif code == "ABS_MT_TRACKING_ID":
            if value.lower() == _TRACKING_UP:
                return self._finish()
            self._down = True  # a new contact began
        elif code == "BTN_TOUCH":
            if value == "DOWN":
                self._down = True
            elif value == "UP":
                return self._finish()

        # Lock the tap point at the first full coordinate pair of the gesture.
        if self._down and not self._captured and self._raw_x is not None and self._raw_y is not None:
            self._tap_x = self._scale_x(self._raw_x)
            self._tap_y = self._scale_y(self._raw_y)
            self._captured = True
        return None

    def _finish(self) -> Optional[Tap]:
        """End the current touch; emit a Tap if we captured an origin."""
        tap = Tap(self._tap_x, self._tap_y) if self._captured else None
        self._down = False
        self._captured = False
        self._raw_x = self._raw_y = None
        return tap


@dataclass(frozen=True)
class TouchDevice:
    """The touchscreen input device and its coordinate range (from ``getevent -p``)."""

    path: str  # e.g. "/dev/input/event1"
    max_x: int
    max_y: int


# "add device 1: /dev/input/event1" and the ABS_MT position lines. getevent -p
# labels axes either symbolically (ABS_MT_POSITION_X, with -l) or by raw hex code
# (0035 = ABS_MT_POSITION_X, 0036 = ABS_MT_POSITION_Y) — accept both.
_ADD_DEVICE = re.compile(r"add device \d+:\s+(\S+)")
_ABS_MAX = re.compile(r"(ABS_MT_POSITION_X|ABS_MT_POSITION_Y|0035|0036)\s*:.*?max\s+(\d+)")
_X_CODES = frozenset(("ABS_MT_POSITION_X", "0035"))


def find_touch_device(getevent_p_output: str) -> Optional[TouchDevice]:
    """Pick the touchscreen from ``adb shell getevent -p`` output.

    ``getevent -p`` lists every input device and the events it supports; the
    touchscreen is the one exposing both ``ABS_MT_POSITION_X`` and
    ``ABS_MT_POSITION_Y`` (multi-touch position). Returns the first such device
    with its reported coordinate maxima, or ``None`` if none is found.

    Args:
        getevent_p_output: full stdout of ``adb shell getevent -p``.

    Returns:
        The touchscreen :class:`TouchDevice`, or ``None``.
    """
    current: Optional[str] = None
    max_x: Optional[int] = None
    max_y: Optional[int] = None

    def _flush() -> Optional[TouchDevice]:
        if current and max_x and max_y:
            return TouchDevice(current, max_x, max_y)
        return None

    for line in getevent_p_output.splitlines():
        add = _ADD_DEVICE.search(line)
        if add:
            done = _flush()
            if done:
                return done
            current, max_x, max_y = add.group(1), None, None
            continue
        abs_max = _ABS_MAX.search(line)
        if abs_max:
            if abs_max.group(1) in _X_CODES:
                max_x = int(abs_max.group(2))
            else:
                max_y = int(abs_max.group(2))
    return _flush()
