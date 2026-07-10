"""
Live session recorder.

Captures a human's manual interactions on a device (via ``adb getevent``) and
turns them into a runnable test — the real implementation behind ``observe
record``. The pieces:

* :mod:`framework.recorder.getevent` — a pure, streaming parser that turns raw
  ``getevent -lt`` lines into screen-space taps (with touch→pixel scaling).
* :mod:`framework.recorder.recorder` — resolves each tap to the element under it
  (reusing the crawler's screen parser + locator ranking) and emits a test via
  the existing codegen targets.
"""

from framework.recorder.getevent import GeteventParser, Tap, TouchDevice, find_touch_device
from framework.recorder.recorder import SessionRecorder, steps_to_model, tap_to_step

__all__ = [
    "GeteventParser",
    "Tap",
    "TouchDevice",
    "find_touch_device",
    "SessionRecorder",
    "steps_to_model",
    "tap_to_step",
]
