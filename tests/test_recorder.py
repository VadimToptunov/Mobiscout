"""The live recorder's pure core: getevent parsing (with touch→pixel scaling),
touchscreen discovery, and resolving a tap to a located test step — plus the
SessionRecorder wrapper (adb argv building, screen-size probing, tap resolution,
the live streaming loop and the codegen emit), with adb/subprocess stubbed."""

from framework.codegen.ir import ActionType
from framework.recorder import GeteventParser, SessionRecorder, find_touch_device, steps_to_model, tap_to_step
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


# --- SessionRecorder ---------------------------------------------------------


def test_cmd_inserts_serial_when_set():
    rec = SessionRecorder("com.myapp", serial="ABC123")
    assert rec._cmd("shell", "wm", "size") == ["adb", "-s", "ABC123", "shell", "wm", "size"]


def test_cmd_omits_serial_when_none():
    rec = SessionRecorder("com.myapp", adb="/opt/adb")
    assert rec._cmd("shell", "foo") == ["/opt/adb", "shell", "foo"]


def test_screen_size_parses_wm_output(monkeypatch):
    rec = SessionRecorder("com.myapp")
    monkeypatch.setattr(rec, "_run", lambda *a: "Physical size: 1080x2340\n")
    assert rec._screen_size() == (1080, 2340)


def test_screen_size_unparseable_returns_zero(monkeypatch):
    rec = SessionRecorder("com.myapp")
    monkeypatch.setattr(rec, "_run", lambda *a: "no size here\n")
    assert rec._screen_size() == (0, 0)


def test_record_tap_appends_resolved_step(monkeypatch):
    rec = SessionRecorder("com.myapp")
    monkeypatch.setattr(rec, "_page_source", lambda: _XML)
    step = rec._record_tap(Tap(250, 440))
    assert step is not None
    assert rec.steps == [step]
    assert rec.skipped == 0
    assert step.selector.value == "com.myapp:id/login"


def test_record_tap_counts_skips_when_unresolved(monkeypatch):
    rec = SessionRecorder("com.myapp")
    monkeypatch.setattr(rec, "_page_source", lambda: _XML)
    step = rec._record_tap(Tap(10, 10))  # frame has no locator
    assert step is None
    assert rec.steps == []
    assert rec.skipped == 1


class _FakePopen:
    """Minimal stand-in for the getevent subprocess: yields canned lines."""

    def __init__(self, lines):
        self.stdout = iter(lines)
        self.terminated = False

    def terminate(self):
        self.terminated = True


def test_record_streams_taps_to_steps(monkeypatch):
    rec = SessionRecorder("com.myapp")
    parser = GeteventParser(touch_max_x=1000, touch_max_y=2000, screen_w=500, screen_h=1000)
    monkeypatch.setattr(rec, "_make_parser", lambda: (parser, "/dev/input/event1"))
    monkeypatch.setattr(rec, "_page_source", lambda: _XML)

    fake = _FakePopen(_TAP_LINES)
    monkeypatch.setattr("framework.recorder.recorder.subprocess.Popen", lambda *a, **k: fake)

    seen = []
    rec.record(on_step=seen.append)

    # The one tap (raw 500,900 -> scaled 250,450) resolves to the login button.
    assert len(rec.steps) == 1
    assert rec.steps[0].selector.value == "com.myapp:id/login"
    assert seen == rec.steps
    assert fake.terminated  # process torn down in finally


def test_emit_no_steps_writes_nothing(tmp_path):
    rec = SessionRecorder("com.myapp")
    summary = rec.emit(str(tmp_path / "out"), target="python_pytest")
    assert summary["steps"] == 0
    assert summary["target"] == "python_pytest"
    # No target subdirectory created when nothing was recorded.
    assert not (tmp_path / "out" / "python_pytest").exists()


def test_emit_writes_test_files_from_steps(tmp_path):
    rec = SessionRecorder("com.myapp")
    rec.steps = [tap_to_step(_XML, x=250, y=440)]
    out = tmp_path / "out"
    summary = rec.emit(str(out), target="python_pytest")
    assert summary["steps"] == 1
    target_dir = out / "python_pytest"
    assert target_dir.exists()
    written = list(target_dir.glob("*"))
    assert written  # emitter produced at least one file
    combined = "\n".join(p.read_text() for p in written if p.is_file())
    assert "com.myapp" in combined
