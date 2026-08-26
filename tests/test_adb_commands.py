"""The adb device-command layer: the exact argv each crawler gesture puts on the
wire, and what the driver reads back off it.

Every command here fails *silently* when it is wrong — a Back that sends HOME
backgrounds the app, an inverted scroll never reveals the fold, unencoded text
truncates at the first space, a skipped clear appends to the old value — none of
which raises. So these pin the commands themselves, not that a method was called.
"""

import framework.crawler.adb_driver as adb
from framework.crawler.adb_driver import AdbCrawlerDriver


def _driver(monkeypatch, reply=None):
    """A driver whose adb calls are recorded, with settling stubbed out — settling
    dumps the UI, which would bury the command under test in adb noise."""
    calls = []

    def run(*args):
        calls.append(args)
        return reply(*args) if reply else ""

    d = AdbCrawlerDriver()
    monkeypatch.setattr(d, "_run", run)
    monkeypatch.setattr(d, "_settle_wait", lambda: None)
    monkeypatch.setattr(adb.time, "sleep", lambda s: None)
    return d, calls


def test_tap_sends_input_tap_at_the_coordinates(monkeypatch):
    d, calls = _driver(monkeypatch)
    d.tap(5, 9)
    assert calls == [("shell", "input", "tap", "5", "9")]


def test_back_sends_the_back_keycode(monkeypatch):
    # 4 = BACK. 3 (HOME) would background the app under test, so every
    # return-to-parent in the crawl would leave the app instead of popping a screen.
    d, calls = _driver(monkeypatch)
    d.back()
    assert calls == [("shell", "input", "keyevent", "4")]


def test_type_text_encodes_spaces_and_shell_metacharacters(monkeypatch):
    # `input text` reads %s as a space and the DEVICE shell re-parses the argv, so
    # a raw value types only up to the first space and hands the rest to the shell.
    d, calls = _driver(monkeypatch)
    d.type_text("S&p 500")
    assert calls == [("shell", "input", "text", "'S&p%s500'")]


def test_clear_field_moves_to_end_then_deletes(monkeypatch):
    # Without this a re-fill (negative probe then positive fill on the same form)
    # appends, leaving the field holding "invalid@valid" — neither branch exercised.
    d, calls = _driver(monkeypatch)
    d.clear_field()
    assert calls[0] == ("shell", "input", "keyevent", "123")  # MOVE_END
    assert calls[1][:4] == ("shell", "input", "keyevent", "67")  # DEL, repeated
    assert set(calls[1][3:]) == {"67"} and len(calls[1][3:]) == 64
    assert len(calls) == 2


def _swipe(calls):
    return next(c for c in calls if "swipe" in c)


def test_scroll_down_swipes_from_lower_to_upper(monkeypatch):
    # "down" must move the content up (finger from low to high on the screen) or
    # everything below the fold stays uncrawled while the crawl looks healthy.
    d, calls = _driver(monkeypatch, reply=lambda *a: "cur=1080x1920" if "displays" in a[-1] else "")
    d.scroll("down")
    cmd = _swipe(calls)
    assert cmd[:3] == ("shell", "input", "swipe")
    x1, from_y, x2, to_y, ms = cmd[3:]
    assert x1 == x2 == "540" and int(from_y) > int(to_y) and ms == "300"  # mid-screen, 1080/2


def test_scroll_up_swipes_the_other_way(monkeypatch):
    d, calls = _driver(monkeypatch, reply=lambda *a: "cur=1080x1920" if "displays" in a[-1] else "")
    d.scroll("up")
    _, from_y, _, to_y, _ = _swipe(calls)[3:]
    assert int(from_y) < int(to_y)


def test_scroll_is_skipped_when_the_screen_size_is_unknown(monkeypatch):
    # A blind swipe on unknown geometry starts off-display and Android drops it.
    d, calls = _driver(monkeypatch)  # every query answers ""
    d.scroll("down")
    assert not any("swipe" in c for c in calls)


_ACTIVITIES = "  topResumedActivity=ActivityRecord{a1b2 u0 com.acme.app/.MainActivity t42}\n"
_FOCUS = "  mCurrentFocus=Window{9f8e u0 com.acme.app/com.acme.app.MainActivity}\n"
_ANR_FOCUS = "  mCurrentFocus=Window{1111 u0 Application Not Responding: com.other.app}\n"


def test_current_package_reads_the_resumed_activity(monkeypatch):
    d, _ = _driver(monkeypatch, reply=lambda *a: _ACTIVITIES if "activities" in a[-1] else "")
    assert d.current_package() == "com.acme.app"


def test_current_package_falls_back_to_focus_ignoring_anr_windows(monkeypatch):
    # No resumed activity (some devices/API levels): read mCurrentFocus instead, but
    # never the ANR window — reporting the crashing app as foreground would make the
    # crawler "recover" away from the app it is crawling.
    def reply(*args):
        if "activities" in args[-1]:
            return ""
        return _ANR_FOCUS + _FOCUS if args[:2] == ("shell", "dumpsys") else ""

    d, _ = _driver(monkeypatch, reply=reply)
    assert d.current_package() == "com.acme.app"


def test_current_package_is_empty_when_nothing_reports_a_foreground_app(monkeypatch):
    d, _ = _driver(monkeypatch)
    assert d.current_package() == ""
