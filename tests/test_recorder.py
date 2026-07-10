"""The live recorder's pure core: getevent parsing (with touch→pixel scaling),
touchscreen discovery, and resolving a tap to a located test step."""

from framework.codegen.ir import ActionType
from framework.recorder import GeteventParser, find_touch_device, steps_to_model, tap_to_step
from framework.recorder.getevent import Tap

# One tap: down at raw (0x1f4=500, 0x384=900), then up. Panel max 1000x2000,
# screen 500x1000 → scale 0.5 → expect (250, 450).
_TAP_LINES = """\
[   1.0] /dev/input/event1: EV_ABS  ABS_MT_TRACKING_ID  0000000b
[   1.0] /dev/input/event1: EV_ABS  ABS_MT_POSITION_X   000001f4
[   1.0] /dev/input/event1: EV_ABS  ABS_MT_POSITION_Y   00000384
[   1.0] /dev/input/event1: EV_KEY  BTN_TOUCH           DOWN
[   1.0] /dev/input/event1: EV_SYN  SYN_REPORT          00000000
[   1.1] /dev/input/event1: EV_ABS  ABS_MT_TRACKING_ID  ffffffff
[   1.1] /dev/input/event1: EV_KEY  BTN_TOUCH           UP
[   1.1] /dev/input/event1: EV_SYN  SYN_REPORT          00000000
""".splitlines()


def test_getevent_parser_emits_scaled_tap():
    parser = GeteventParser(touch_max_x=1000, touch_max_y=2000, screen_w=500, screen_h=1000)
    taps = [t for line in _TAP_LINES if (t := parser.feed(line)) is not None]
    assert taps == [Tap(250, 450)]


def test_getevent_parser_identity_when_no_max():
    parser = GeteventParser(touch_max_x=0, touch_max_y=0, screen_w=500, screen_h=1000)
    taps = [t for line in _TAP_LINES if (t := parser.feed(line)) is not None]
    assert taps == [Tap(500, 900)]  # raw values passed through unscaled


def test_find_touch_device_picks_the_multitouch_screen():
    out = """\
add device 1: /dev/input/event0
  name:     "some-buttons"
    KEY (0001): ...
add device 2: /dev/input/event1
  name:     "touchscreen"
    ABS (0003): ABS_MT_POSITION_X : value 0, min 0, max 1439, fuzz 0, flat 0
                ABS_MT_POSITION_Y : value 0, min 0, max 2559, fuzz 0, flat 0
"""
    device = find_touch_device(out)
    assert device is not None
    assert device.path == "/dev/input/event1"
    assert (device.max_x, device.max_y) == (1439, 2559)


def test_find_touch_device_none_when_absent():
    assert find_touch_device("add device 1: /dev/input/event0\n  KEY (0001): ...\n") is None


_XML = """<?xml version="1.0"?>
<hierarchy>
  <node class="android.widget.FrameLayout" bounds="[0,0][500,1000]" clickable="false" package="com.myapp">
    <node resource-id="com.myapp:id/login" text="Sign in" class="android.widget.Button"
          clickable="true" bounds="[100,400][400,480]" package="com.myapp"/>
  </node>
</hierarchy>"""


def test_tap_to_step_resolves_element_under_point():
    step = tap_to_step(_XML, x=250, y=440)
    assert step is not None
    assert step.action is ActionType.TAP
    # Smallest containing element is the button, not the full-screen frame.
    assert step.selector.value == "com.myapp:id/login"
    assert step.description == "Sign in"


def test_tap_to_step_returns_none_off_target():
    assert tap_to_step(_XML, x=10, y=10) is None  # frame has no locator (no id/text)


def test_steps_to_model_prepends_launch_and_wraps_one_case():
    step = tap_to_step(_XML, x=250, y=440)
    model = steps_to_model("com.myapp", [step])
    assert model.app_package == "com.myapp"
    assert len(model.cases) == 1
    steps = model.cases[0].steps
    assert steps[0].action is ActionType.LAUNCH
    assert steps[1].action is ActionType.TAP
