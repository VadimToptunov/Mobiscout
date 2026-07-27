"""Unit tests for negative-path form probing (`_probe_negative_form`).

The crawl must exercise forms with *invalid* input, not only valid — submitting
bad data so the validation-error (or wrongly-advanced) state is discovered and
turned into a test. These pin that behaviour with a fake driver.
"""

from framework.crawler.app_crawler import AppCrawler, _invalid_value, _sample_value
from framework.crawler.models import CrawlElement, CrawlResult, CrawlScreen

APP = "com.example.app"


def _input(rid, cls="android.widget.EditText"):
    return CrawlElement(
        resource_id=rid,
        text="",
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


class FormDriver:
    """Serves a login form; a submit tap moves to whatever page source is set as
    the 'after' screen (an error banner by default). Records taps and typed text."""

    def __init__(self, after_source):
        self.after_source = after_source
        self.on_form = True
        self.taps = []
        self.typed = []

    def current_package(self):
        return APP

    def _form_source(self):
        return (
            '<hierarchy rotation="0">'
            '<node class="android.widget.EditText" resource-id="id/email" text="" '
            'content-desc="Email" clickable="true" bounds="[0,0][200,60]"/>'
            '<node class="android.widget.Button" resource-id="id/login" text="Log In" '
            'content-desc="" clickable="true" bounds="[0,100][200,160]"/>'
            "</hierarchy>"
        )

    def page_source(self):
        return self._form_source() if self.on_form else self.after_source

    def tap(self, x, y):
        self.taps.append((x, y))
        if 100 <= y <= 160:  # the login button
            self.on_form = False

    def type_text(self, value):
        self.typed.append(value)

    def hide_keyboard(self):
        pass

    def back(self):
        self.on_form = True  # returning to the form

    def refresh(self):
        return self.page_source()


_ERROR_SOURCE = (
    '<hierarchy rotation="0">'
    '<node class="android.widget.TextView" resource-id="id/err" text="Invalid email" '
    'content-desc="" clickable="false" bounds="[0,0][200,40]"/>'
    "</hierarchy>"
)


def _crawler(driver):
    return AppCrawler(driver, APP, max_steps=50)


def test_invalid_value_is_deliberately_bad():
    assert _invalid_value(_input("id/email")) == "not-an-email"
    assert _invalid_value(_input("id/amount")) == "-1"
    # A field with no strongly-typed rule yields "" (skip, leave blank).
    assert _invalid_value(_input("id/note")) == ""


def test_negative_probe_types_invalid_and_records_error_state():
    driver = FormDriver(_ERROR_SOURCE)
    result = CrawlResult()
    screen = CrawlScreen(
        fingerprint="form",
        elements=[
            _input(
                "id/email",
            ),
            _button("id/login", "Log In"),
        ],
    )
    _crawler(driver)._probe_negative_form(result, screen)

    # It typed the *invalid* email, not the valid one.
    assert driver.typed == ["not-an-email"]
    assert _sample_value(_input("id/email")) not in driver.typed
    # It submitted and recorded a transition to the discovered error state.
    assert len(result.transitions) == 1
    src, elem, dst = result.transitions[0]
    assert src == "form" and elem.resource_id == "id/login" and dst != "form"
    assert dst in result.screens  # the error state is now a discovered screen


def test_negative_probe_runs_once_per_form():
    driver = FormDriver(_ERROR_SOURCE)
    result = CrawlResult()
    screen = CrawlScreen(fingerprint="form", elements=[_input("id/email"), _button("id/login", "Log In")])
    c = _crawler(driver)
    c._probe_negative_form(result, screen)
    typed_after_first = list(driver.typed)
    c._probe_negative_form(result, screen)  # second call is a no-op
    assert driver.typed == typed_after_first


def test_no_submit_control_is_skipped():
    driver = FormDriver(_ERROR_SOURCE)
    result = CrawlResult()
    # Input but no submit-like button -> not a submittable form.
    screen = CrawlScreen(fingerprint="form", elements=[_input("id/email"), _button("id/help", "Help")])
    _crawler(driver)._probe_negative_form(result, screen)
    assert driver.typed == []
    assert result.transitions == []


def test_no_input_is_skipped():
    driver = FormDriver(_ERROR_SOURCE)
    result = CrawlResult()
    screen = CrawlScreen(fingerprint="scr", elements=[_button("id/login", "Log In")])
    _crawler(driver)._probe_negative_form(result, screen)
    assert result.transitions == []


def test_handle_form_does_both_negative_then_valid():
    driver = FormDriver(_ERROR_SOURCE)
    result = CrawlResult()
    screen = CrawlScreen(fingerprint="form", elements=[_input("id/email"), _button("id/login", "Log In")])
    _crawler(driver)._handle_form(result, screen)
    # Negative branch typed the invalid value; positive branch then typed the valid one.
    assert "not-an-email" in driver.typed
    assert "test@example.com" in driver.typed
    assert driver.typed.index("not-an-email") < driver.typed.index("test@example.com")
