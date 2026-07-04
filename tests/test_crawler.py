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


def test_build_test_model_asserts_noninteractive_text_compose():
    """Compose: the tappable node is empty but a sibling carries the text — the
    generated model must still assert that visible text."""
    from framework.crawler.app_crawler import CrawlResult, parse_screen
    from framework.crawler.to_codegen import build_test_model
    from framework.codegen.ir import SelectorStrategy

    xml = _screen(
        _node("", "", True, (0, 0, 100, 50)),  # clickable wrapper, no locator
        _node("Generate Contacts", "", False, (0, 60, 100, 110)),  # text label, not clickable
    )
    screen = parse_screen(xml)
    result = CrawlResult(screens={screen.fingerprint: screen})
    model = build_test_model(result, app_package=APP)
    values = [s.selector.value for c in model.cases for s in c.steps if s.selector]
    assert "Generate Contacts" in values


# --- cross-platform parsing --------------------------------------------------

IOS_XML = """<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="MyApp" x="0" y="0" width="390" height="844">
  <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="" label="Welcome" x="20" y="50" width="200" height="30"/>
  <XCUIElementTypeButton type="XCUIElementTypeButton" name="login_btn" label="Log In" enabled="true" x="20" y="100" width="200" height="44"/>
</XCUIElementTypeApplication>"""


def test_parse_ios_screen():
    screen = parse_screen(IOS_XML)
    assert screen.platform == "ios"
    btn = [e for e in screen.elements if e.class_name == "Button"][0]
    assert btn.content_desc == "login_btn"  # iOS name -> accessibility id
    assert btn.text == "Log In"  # iOS label -> text
    assert btn.clickable and btn.bounds == (20, 100, 220, 144)
    assert btn.center == (120, 122)


def test_detects_hybrid_webview():
    android = _screen(
        '<node class="android.webkit.WebView" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[0,0][100,100]"/>'
    )
    assert parse_screen(android).hybrid is True
    assert parse_screen(SCREENS["login"]).hybrid is False  # pure native


def test_ios_crawl_builds_accessibility_selectors():
    from framework.crawler.app_crawler import CrawlResult
    from framework.crawler.to_codegen import build_test_model
    from framework.codegen.ir import SelectorStrategy

    screen = parse_screen(IOS_XML)
    model = build_test_model(CrawlResult(screens={screen.fingerprint: screen}), app_package="MyApp")
    selectors = [s.selector for c in model.cases for s in c.steps if s.selector]
    # iOS accessibility id must become an ACCESSIBILITY_ID selector (cross-platform)
    assert any(s.strategy is SelectorStrategy.ACCESSIBILITY_ID and s.value == "login_btn" for s in selectors)


def test_detects_toolkit_native_flutter_hybrid():
    native = parse_screen(SCREENS["login"])
    assert native.toolkit == "native" and not native.hybrid

    flutter = parse_screen(
        '<node class="io.flutter.embedding.android.FlutterView" resource-id="" text="" '
        'content-desc="" clickable="false" bounds="[0,0][400,800]"/>'
    )
    assert flutter.toolkit == "flutter"

    hybrid = parse_screen(
        '<node class="android.webkit.WebView" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[0,0][400,800]"/>'
    )
    assert hybrid.toolkit == "hybrid" and hybrid.hybrid is True


def test_crawler_ignores_foreign_package_elements():
    """Elements owned by another package (system UI / launcher) must never be
    tapped — this is what caused random apps to launch."""
    from framework.crawler.app_crawler import parse_screen

    xml = (
        "<hierarchy>"
        '<node class="android.widget.Button" resource-id="" text="App Button" content-desc="" '
        f'package="{APP}" clickable="true" bounds="[0,0][100,50]"/>'
        '<node class="android.widget.FrameLayout" resource-id="android:id/navigationBarBackground" '
        'text="" content-desc="" package="android" clickable="true" bounds="[0,900][100,950]"/>'
        "</hierarchy>"
    )

    class OneScreen:
        def __init__(self):
            self.pkg = APP
            self.tapped = []

        def page_source(self):
            return xml

        def current_package(self):
            return self.pkg

        def back(self):
            pass

        def tap(self, x, y):
            for e in parse_screen(xml).elements:
                x1, y1, x2, y2 = e.bounds
                if x1 <= x <= x2 and y1 <= y <= y2:
                    self.tapped.append(e.package)

    d = OneScreen()
    AppCrawler(d, APP, max_steps=10).crawl()
    assert "android" not in d.tapped  # never tapped the system nav bar


def test_crawler_does_not_start_off_app():
    class Foreign:
        def page_source(self):
            return SCREENS["login"]

        def current_package(self):
            return "com.android.launcher"

        def back(self):
            pass

        def tap(self, x, y):
            raise AssertionError("must not tap when not on the app")

    result = AppCrawler(Foreign(), APP).crawl()
    assert result.screens == {}
