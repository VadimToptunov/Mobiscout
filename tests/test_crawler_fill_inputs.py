"""Unit tests for the crawler's form-filling step (`_fill_inputs`).

A tap-only crawl stalls at any screen that gates progress behind text entry
(login, exchange amount, search); these pin that the crawler now types a
sample value into each text field so following button taps can submit — and
that it does so without breaking on drivers that can't type.
"""

from framework.crawler.app_crawler import AppCrawler, _sample_value
from framework.crawler.models import CrawlElement, CrawlScreen

APP = "com.example.app"


def _input(rid, text="", cls="android.widget.EditText"):
    return CrawlElement(
        resource_id=rid,
        text=text,
        content_desc="",
        class_name=cls,
        clickable=True,
        bounds=(0, 0, 200, 60),
        package="",
        focusable=True,
    )


def _button(rid, text):
    return CrawlElement(
        resource_id=rid,
        text=text,
        content_desc="",
        class_name="android.widget.Button",
        clickable=True,
        bounds=(0, 100, 200, 160),
        package="",
    )


class RecordingDriver:
    """Records taps and typed text; can optionally lack `type_text`/`hide_keyboard`,
    or (opt-in) provide `clear_field`. `events` logs tap/clear/type in call order."""

    def __init__(self, can_type=True, can_hide=True, can_clear=False):
        self.taps = []
        self.typed = []
        self.hidden = 0
        self.cleared = 0
        self.events = []
        if can_type:
            self.type_text = self._type_text
        if can_hide:
            self.hide_keyboard = self._hide_keyboard
        if can_clear:
            self.clear_field = self._clear_field

    def current_package(self):
        return APP

    def tap(self, x, y):
        self.taps.append((x, y))
        self.events.append("tap")

    def _type_text(self, value):
        self.typed.append(value)
        self.events.append("type")

    def _clear_field(self):
        self.cleared += 1
        self.events.append("clear")

    def _hide_keyboard(self):
        self.hidden += 1


def _crawler(driver):
    return AppCrawler(driver, APP, max_steps=1)


def test_fills_each_input_and_dismisses_keyboard():
    driver = RecordingDriver()
    screen = CrawlScreen(
        fingerprint="fp",
        elements=[
            _input("id/email", cls="android.widget.EditText"),
            _input("id/password", cls="android.widget.EditText"),
            _button("id/submit", "Submit"),
        ],
    )
    _crawler(driver)._fill_inputs(screen)

    # Both inputs typed into (not the button); keyboard dismissed once.
    assert len(driver.typed) == 2
    assert driver.hidden == 1
    # Each input was tapped to focus before typing.
    assert len(driver.taps) == 2


def test_clears_each_field_before_typing_when_supported():
    # When the driver can clear, a field is cleared BEFORE typing so a re-fill (negative
    # probe then positive fill, or a revisit) replaces the text instead of appending —
    # otherwise a field holds "invalid@valid" and neither branch is really exercised.
    driver = RecordingDriver(can_clear=True)
    screen = CrawlScreen(fingerprint="fp", elements=[_input("id/email"), _button("id/submit", "Submit")])
    _crawler(driver)._fill_inputs(screen)
    assert driver.cleared == 1
    assert driver.events == ["tap", "clear", "type"]  # focus, then clear, then type


def test_skips_foreign_package_inputs():
    driver = RecordingDriver()
    foreign = _input("id/other")
    foreign.package = "com.other.app"
    screen = CrawlScreen(fingerprint="fp", elements=[foreign])
    _crawler(driver)._fill_inputs(screen)
    assert driver.typed == []


def test_no_inputs_is_a_noop():
    driver = RecordingDriver()
    screen = CrawlScreen(fingerprint="fp", elements=[_button("id/x", "Go")])
    _crawler(driver)._fill_inputs(screen)
    assert driver.typed == []
    assert driver.hidden == 0  # keyboard never shown -> never dismissed


def test_survives_driver_without_type_text():
    driver = RecordingDriver(can_type=False)
    screen = CrawlScreen(fingerprint="fp", elements=[_input("id/email")])
    # Must not raise even though the driver can't type.
    _crawler(driver)._fill_inputs(screen)
    assert driver.typed == []


def test_survives_driver_without_hide_keyboard():
    driver = RecordingDriver(can_hide=False)
    screen = CrawlScreen(fingerprint="fp", elements=[_input("id/email")])
    _crawler(driver)._fill_inputs(screen)  # no hide_keyboard attribute -> no crash
    assert len(driver.typed) == 1


def test_sample_value_infers_type_from_hints():
    assert _sample_value(_input("id/email", text="Email")) == "test@example.com"
    assert "@" not in _sample_value(_input("id/user", text="Name"))
    pwd = _input("id/pw")
    pwd.password = True
    pwd.class_name = "android.widget.EditText"
    # password field by label
    assert _sample_value(_input("id/password", text="Password")) == "Password123!"
    assert _sample_value(_input("id/amount", text="Amount")) == "10"
    assert _sample_value(_input("id/search", text="Search")) == "test"
    assert _sample_value(_input("id/generic", text="Note")) == "Test"


def test_graph_and_crawler_share_one_form_value_vocabulary():
    """The live crawl (app_crawler) and codegen (graph) must fill forms with the
    exact same values — they import the single definition, so no desync is
    possible (previously graph had a copy missing the amount branch, so a positive
    test typed 'Test' into an amount field the crawl filled with '10')."""
    from framework.crawler import app_crawler, graph

    assert app_crawler._sample_value is graph._sample_value
    assert app_crawler._invalid_value is graph._invalid_value
    assert app_crawler._SUBMIT_LABELS is graph._SUBMIT_LABELS
    # An amount field gets a numeric sample through the shared definition.
    assert graph._sample_value(_input("id/amount", text="Amount")) == "10"
