"""Batch 3 — anti-crawl / flaky-backend resilience (device-free):

  * root/jailbreak/emulator integrity screens are terminal dead-ends; and
  * a transient error screen ("no connection / try again") is retried, and the
    crawler's read recovers to the real content behind it — a persistent error is
    mapped once, not looped on.
"""

from framework.crawler.app_crawler import AppCrawler, parse_screen
from framework.crawler.obstacles import error_retry, terminal_obstacle

APP = "com.example.app"


def _n(text, bounds, cls="android.widget.Button"):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="{cls}" resource-id="" text="{text}" content-desc="" '
        f'clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _screen(*nodes):
    return parse_screen('<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>")


class _Rec:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))


def test_integrity_blocks_are_terminal():
    assert terminal_obstacle(_screen(_n("This device is rooted", (0, 0, 300, 40)))) == "integrity_block"
    assert terminal_obstacle(_screen(_n("Jailbreak detected", (0, 0, 300, 40)))) == "integrity_block"
    assert terminal_obstacle(_screen(_n("This app cannot run on an emulator", (0, 0, 300, 40)))) == "integrity_block"
    assert terminal_obstacle(_screen(_n("Welcome home", (0, 0, 300, 40)))) is None


def test_error_retry_taps_a_retry_control():
    scr = _screen(_n("No connection. Please try again.", (0, 0, 300, 40)), _n("Retry", (0, 50, 100, 90)))
    d = _Rec()
    assert error_retry(d, scr) == "retry"
    assert d.taps == [(50, 70)]


def test_error_without_retry_control_is_left_alone():
    # An error screen with no retry control is a genuine state to record, not tap.
    scr = _screen(_n("Something went wrong", (0, 0, 300, 40)), _n("Go to settings", (0, 50, 150, 90)))
    d = _Rec()
    assert error_retry(d, scr) is None
    assert d.taps == []


def test_no_retry_on_healthy_screen():
    scr = _screen(_n("Account balance", (0, 0, 300, 40)), _n("Reload data", (0, 50, 150, 90)))
    d = _Rec()
    # "Reload" is a retry label, but there's no error text — don't touch it.
    assert error_retry(d, scr) is None
    assert d.taps == []


class _FlakyDriver:
    """First read is a transient error with a Retry; any tap 'recovers' the backend
    so the next read is the real content."""

    def __init__(self):
        self.recovered = False

    def page_source(self):
        if self.recovered:
            return '<hierarchy rotation="0">' + _n("Account balance", (0, 0, 200, 40)) + "</hierarchy>"
        return (
            '<hierarchy rotation="0">'
            + _n("No internet connection", (0, 0, 200, 40))
            + _n("Try again", (0, 50, 100, 90))
            + "</hierarchy>"
        )

    def current_package(self):
        return APP

    def back(self):
        pass

    def tap(self, x, y):
        self.recovered = True


def test_read_recovers_from_transient_error():
    crawler = AppCrawler(_FlakyDriver(), APP)
    screen = crawler._read_content_screen()
    labels = " ".join(e.label for e in screen.elements).lower()
    assert "account balance" in labels  # retried past the error to the real content
    assert "try again" not in labels
