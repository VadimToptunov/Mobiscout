"""Unit tests for the autonomous app crawler (no device — fake driver)."""

from framework.crawler.app_crawler import AppCrawler, parse_screen

APP = "com.example.app"


def _node(label, rid, clickable, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.Button" resource-id="{rid}" text="{label}" '
        f'content-desc="" clickable="{"true" if clickable else "false"}" '
        f'bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _screen(*nodes):
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


# A small app:
#   login  -- "Login" --> home       -- "Settings" --> settings (has a blocked "Logout")
#          -- "Help"  --> help (leaf)
#   settings -- "Open Store" --> external app (must be backed out of)
SCREENS = {
    "login": _screen(
        _node("Login", "id/login", True, (0, 0, 100, 50)),
        _node("Help", "id/help", True, (0, 60, 100, 110)),
    ),
    "home": _screen(_node("Settings", "id/settings", True, (0, 0, 100, 50))),
    "help": _screen(_node("Back home", "id/nope", False, (0, 0, 100, 50))),
    "settings": _screen(
        _node("Logout", "id/logout", True, (0, 0, 100, 50)),
        _node("Open Store", "id/store", True, (0, 60, 100, 110)),
    ),
}
TRANSITIONS = {
    ("login", "Login"): "home",
    ("login", "Help"): "help",
    ("home", "Settings"): "settings",
    ("settings", "Open Store"): "<foreign>",
    # ("settings", "Logout") intentionally absent — must never be tapped anyway
}


class FakeDriver:
    def __init__(self):
        self.current = "login"
        self.nav = []
        self.pkg = APP
        self.tapped_labels = []

    def page_source(self):
        return SCREENS[self.current]

    def current_package(self):
        return self.pkg

    def back(self):
        self.pkg = APP
        if self.nav:
            self.current = self.nav.pop()

    def _label_at(self, x, y):
        for e in parse_screen(SCREENS[self.current]).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                return e.label
        return ""

    def tap(self, x, y):
        label = self._label_at(x, y)
        self.tapped_labels.append(label)
        target = TRANSITIONS.get((self.current, label))
        if target == "<foreign>":
            self.pkg = "com.other.store"  # left the app
        elif target:
            self.nav.append(self.current)
            self.current = target


def test_crawler_discovers_all_reachable_screens():
    driver = FakeDriver()
    result = AppCrawler(driver, APP, max_steps=100).crawl()
    # login + home + help + settings = 4 unique screens
    assert len(result.screens) == 4
    assert any(lbl == "Login" for _, lbl, _ in result.transitions)
    assert any(lbl == "Settings" for _, lbl, _ in result.transitions)


def test_crawler_never_taps_blocklisted_elements():
    driver = FakeDriver()
    AppCrawler(driver, APP, max_steps=100).crawl()
    assert "Logout" not in driver.tapped_labels


def test_crawler_recovers_from_leaving_the_app():
    driver = FakeDriver()
    result = AppCrawler(driver, APP, max_steps=100).crawl()
    # After tapping "Open Store" (foreign), the crawler backs out and finishes
    # cleanly, having returned to the app package.
    assert "Open Store" in driver.tapped_labels
    assert driver.current_package() == APP


def test_crawler_respects_step_budget():
    driver = FakeDriver()
    result = AppCrawler(driver, APP, max_steps=3).crawl()
    assert result.steps <= 3


def test_fingerprint_is_structural_not_textual():
    a = parse_screen(_screen(_node("Sign in", "id/login", True, (0, 0, 100, 50))))
    b = parse_screen(_screen(_node("Log in now", "id/login", True, (0, 0, 100, 50))))
    # Same structure (class/id/clickable), different text -> same fingerprint.
    assert a.fingerprint == b.fingerprint and a.fingerprint != ""


def test_parse_screen_extracts_interactive_elements():
    screen = parse_screen(SCREENS["login"])
    assert len(screen.interactive()) == 2
    assert screen.elements[0].center == (50, 25)


def test_crawl_result_generates_compilable_tests(tmp_path):
    """Golden path end-to-end: crawl -> IR -> codegen -> valid Python."""
    import py_compile
    from framework.crawler.to_codegen import build_test_model
    from framework.codegen import get_emitter

    driver = FakeDriver()
    result = AppCrawler(driver, APP, max_steps=100).crawl()
    model = build_test_model(result, app_package=APP, app_activity=".MainActivity")
    assert model.cases  # the crawl produced screens with elements

    out = get_emitter("python_pytest").emit(model)
    for name, content in out.items():
        f = tmp_path / name
        f.write_text(content, encoding="utf-8", newline="\n")
        py_compile.compile(str(f), doraise=True)
