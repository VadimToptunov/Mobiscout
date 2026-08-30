"""_clear_blocking_dialog must match its safe/unsafe labels as whole words. A bare
substring check fired "ok" on "Book"/"Cookies"/"Unlock" and "allow" on "Allowance",
so the crawl tapped an ordinary control believing it dismissed a system dialog."""

from framework.crawler.app_crawler import AppCrawler

APP = "com.example.app"


def _node(text, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.Button" resource-id="" text="{text}" content-desc="" '
        f'clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _screen(*nodes):
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


class OneScreenDriver:
    def __init__(self, xml):
        self.xml = xml
        self.tapped = []
        self.pkg = APP

    def page_source(self):
        return self.xml

    def current_package(self):
        return self.pkg

    def tap(self, x, y):
        self.tapped.append((x, y))

    def back(self):
        pass


def _tapped_label(xml):
    driver = OneScreenDriver(xml)
    crawler = AppCrawler(driver, APP)
    dismissed = crawler._clear_blocking_dialog()
    if not dismissed:
        return None
    x, y = driver.tapped[-1]
    from framework.crawler.app_crawler import parse_screen

    for e in parse_screen(xml).elements:
        x1, y1, x2, y2 = e.bounds
        if x1 <= x <= x2 and y1 <= y <= y2:
            return e.label
    return None


def test_does_not_tap_ordinary_controls_that_merely_contain_a_safe_word():
    # "Book"⊃ok, "Cookies"⊃ok, "Unlock"⊃ok, "Allowance"⊃allow — none is a dialog button.
    for word in ("Book now", "Cookies", "Unlock", "Allowance"):
        xml = _screen(_node(word, (0, 0, 300, 80)))
        assert _tapped_label(xml) is None, f"tapped {word!r} as if it were a dialog button"


def test_taps_a_real_ok_dialog_button():
    xml = _screen(
        _node("This app needs permission", (0, 0, 300, 60)),
        _node("OK", (0, 100, 300, 180)),
    )
    assert _tapped_label(xml) == "OK"


def test_skips_the_negative_button_of_a_permission_dialog():
    # "Allow" is safe, but "Don't allow" must never be tapped.
    xml = _screen(
        _node("Don't allow", (0, 0, 150, 80)),
        _node("Allow", (150, 0, 300, 80)),
    )
    assert _tapped_label(xml) == "Allow"
