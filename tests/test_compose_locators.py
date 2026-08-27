"""Jetpack Compose exposes every tappable control as an anonymous `android.view.View`
whose visible caption sits on a NON-clickable child::

    [clickable] android.view.View  ""
        TextView  "Add plant"

Read literally, such a control has no label — so it gets no locator, generated tests
can't target it, and coverage reports 0% on an app the crawl actually walked. Found by
crawling Google's Sunflower on a real emulator: 2 screens, 0% element coverage. Lifting
the descendant's caption onto the clickable node took the same app to 4 screens / 94%.

Compose is the default for new Android apps, so these pin that behaviour.
"""

from framework.crawler.coverage_report import COMPOSE_TESTTAG_DOCS, IOS_A11Y_DOCS, locator_advice
from framework.crawler.models import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.parse import parse_screen


def _compose_button(caption: str, bounds: str, tag: str = "TextView") -> str:
    """A Compose control: anonymous clickable wrapper + labelled, non-clickable child."""
    return (
        f'<node class="android.view.View" resource-id="" text="" content-desc="" '
        f'clickable="true" bounds="{bounds}">'
        f'<node class="android.widget.{tag}" resource-id="" text="{caption}" content-desc="" '
        f'clickable="false" bounds="{bounds}"/>'
        f"</node>"
    )


def _screen(*nodes: str) -> str:
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


def test_compose_control_takes_the_caption_from_its_child():
    screen = parse_screen(_screen(_compose_button("Add plant", "[0,0][300,80]")))
    tappable = screen.interactive()
    assert [e.label for e in tappable] == ["Add plant"]


def test_caption_is_read_through_an_intermediate_wrapper():
    # Compose nests several layout views between the clickable node and the text.
    nested = (
        '<node class="android.view.View" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[0,0][300,80]">'
        '<node class="android.view.View" resource-id="" text="" content-desc="" '
        'clickable="false" bounds="[0,0][300,80]">'
        '<node class="android.widget.TextView" resource-id="" text="Plant list" content-desc="" '
        'clickable="false" bounds="[0,0][300,80]"/>'
        "</node></node>"
    )
    assert [e.label for e in parse_screen(_screen(nested)).interactive()] == ["Plant list"]


def test_a_nested_control_keeps_its_own_caption():
    # A clickable inside a clickable (a row with its own action button): the outer node
    # must not steal the inner one's label, or both tests would target the same control.
    outer = (
        '<node class="android.view.View" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[0,0][300,80]">'
        '<node class="android.view.View" resource-id="" text="" content-desc="" '
        'clickable="true" bounds="[200,0][300,80]">'
        '<node class="android.widget.TextView" resource-id="" text="Share" content-desc="" '
        'clickable="false" bounds="[200,0][300,80]"/>'
        "</node></node>"
    )
    labels = [e.label for e in parse_screen(_screen(outer)).interactive()]
    assert "Share" in labels  # the inner control keeps it
    assert labels.count("Share") == 1  # and the outer one did not take it too


def test_a_control_with_its_own_label_is_untouched():
    native = (
        '<node class="android.widget.Button" resource-id="id/ok" text="OK" content-desc="" '
        'clickable="true" bounds="[0,0][100,40]"/>'
    )
    element = parse_screen(_screen(native)).interactive()[0]
    assert element.label == "OK" and element.content_desc == ""


def _ios_result(identified: int, total: int) -> CrawlResult:
    """An iOS screen where `identified` of `total` controls carry a real identifier.
    XCUITest echoes the label into `name` when the app sets none — that is the un-identified
    case, and it is what the advice is about."""
    elements = []
    for i in range(total):
        label = f"Button {i}"
        elements.append(
            CrawlElement(
                resource_id=f"btn_{i}" if i < identified else label,  # echo == no identifier
                text="",
                content_desc=label,
                class_name="XCUIElementTypeButton",
                clickable=True,
                bounds=(0, i * 40, 100, i * 40 + 40),
            )
        )
    return CrawlResult(screens={"fp": CrawlScreen("fp", elements, platform="ios")})


def test_ios_advice_fires_when_controls_only_echo_their_label():
    advice = locator_advice("native", "ios", _ios_result(identified=0, total=6))
    assert IOS_A11Y_DOCS in advice and "accessibilityIdentifier" in advice


def test_ios_advice_is_silent_when_the_app_sets_identifiers():
    assert locator_advice("native", "ios", _ios_result(identified=6, total=6)) == ""


def test_compose_advice_names_the_debug_variant_only():
    advice = locator_advice("compose", "android", CrawlResult())
    assert COMPOSE_TESTTAG_DOCS in advice
    # Publishing internal tags as resource-ids is a test-build concern, never a release one.
    assert "debug/test build variant only" in advice


def test_no_advice_for_a_plain_android_app():
    assert locator_advice("native", "android", CrawlResult()) == ""


# --- a screen that gets bounced out of keeps its unfinished work ---------------------
#
# Found on Sunflower: from the plant list the crawl tapped the "My garden" tab, landed on a
# screen it had already mapped, and Back did not come back — so the plant-list frame was
# abandoned half-explored and not one plant was ever opened. The crawl parks a bounced
# frame's leftovers and picks them up the next time it stands on that screen.

_APP = "com.example.app"


def _node(text, bounds, rid="", cls="android.widget.Button", clickable="true"):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="{cls}" resource-id="{rid}" text="{text}" content-desc="" '
        f'clickable="{clickable}" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _page(*nodes):
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


# home --Open list--> list; list has a "Home" tab that bounces back, plus an Item to open.
_PAGES = {
    # Two ways in, as in Sunflower (its "Plant list" tab and its empty-garden "Add plant"
    # both open the list). That second route is what makes the parked work reachable again:
    # parking preserves the leftovers, revisiting is what spends them.
    "home": _page(
        _node("Open list", (0, 0, 200, 40), "id/open"),
        _node("Browse", (0, 60, 200, 100), "id/browse"),
    ),
    "list": _page(
        _node("Home", (0, 0, 200, 40), "id/tab_home"),  # tapped first — bounces to home
        _node("Item", (0, 60, 200, 100), "id/item"),  # ...leaving this unexplored
    ),
    "detail": _page(
        _node("Detail body", (0, 0, 200, 40), "id/detail", cls="android.widget.TextView", clickable="false")
    ),
}
_MOVES = {
    ("home", "Open list"): "list",
    ("home", "Browse"): "list",
    ("list", "Home"): "home",
    ("list", "Item"): "detail",
}


class _BouncingApp:
    """Back never returns to the list, so the crawl can only finish it by coming back."""

    def __init__(self):
        self.current = "home"
        self.tapped = []

    def page_source(self):
        return _PAGES[self.current]

    def current_package(self):
        return _APP

    def back(self):
        self.current = "home"  # Back always lands on home, never back on the list

    def type_text(self, text):
        pass

    def tap(self, x, y):
        label = ""
        for e in parse_screen(self.page_source()).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2 and e.clickable:
                label = e.label
                break
        self.tapped.append(label)
        self.current = _MOVES.get((self.current, label), self.current)


def test_a_bounced_screen_is_finished_on_the_next_visit():
    from framework.crawler.app_crawler import AppCrawler

    driver = _BouncingApp()
    result = AppCrawler(driver, _APP, max_steps=60, max_depth=8).crawl()
    # The tab bounced the crawl off the list before it reached "Item"; it had to return.
    assert "Item" in driver.tapped, f"never opened the item: {driver.tapped}"
    labels = {e.label for s in result.screens.values() for e in s.elements}
    assert "Detail body" in labels  # ...and the screen behind it was mapped


# --- a WebView screen is read after its document loads ------------------------------
#
# Found on a banking app whose sign-in opens a WebView. A WebView loads asynchronously by
# definition, so the first read returns the native shell — a chrome bar and a Cancel
# button, enough controls to look settled. The crawl fingerprinted that shell, found no
# username or password field, tapped Cancel and left: everything behind the login stayed
# unmapped. A hybrid screen now always gets a second read.

# The shell carries SEVERAL controls (a browser chrome bar has Cancel, Back, Reload...),
# so it looks settled to the content-count check — which is exactly why only the hybrid
# flag saves it. A one-control shell would be re-read anyway and prove nothing.
_SHELL = _page(
    _node("Cancel", (0, 0, 100, 40), "id/cancel"),
    _node("Back", (110, 0, 200, 40), "id/back"),
    _node("Reload", (210, 0, 300, 40), "id/reload"),
    _node("Sign in", (0, 45, 300, 55), "id/title", clickable="false"),
)
_LOADED = _page(
    _node("Cancel", (0, 0, 100, 40), "id/cancel"),
    _node("", (0, 60, 300, 100), "id/user", cls="android.widget.EditText"),
    _node("", (0, 110, 300, 150), "id/pass", cls="android.widget.EditText"),
    _node("Log in", (0, 160, 200, 200), "id/submit"),
    # A WebView in the tree is what marks the screen hybrid.
    _node("", (0, 0, 300, 400), "id/web", cls="android.webkit.WebView", clickable="false"),
)
_SHELL_HYBRID = _SHELL.replace(
    "</hierarchy>",
    _node("", (0, 0, 300, 400), "id/web", cls="android.webkit.WebView", clickable="false") + "</hierarchy>",
)


class _LateWebView:
    """Serves the WebView shell first and the loaded document on refresh()."""

    def __init__(self):
        self.reads = 0

    def page_source(self):
        self.reads += 1
        return _SHELL_HYBRID

    def refresh(self, wait=1.0):
        return _LOADED

    def current_package(self):
        return _APP

    def tap(self, x, y):
        pass

    def back(self):
        pass

    def type_text(self, text):
        pass


def test_a_hybrid_screen_is_re_read_so_its_form_is_seen():
    from framework.crawler.app_crawler import AppCrawler

    driver = _LateWebView()
    settled = AppCrawler(driver, _APP)._await_content(parse_screen(_SHELL_HYBRID))
    labels = {e.label for e in settled.elements}
    assert "Log in" in labels, f"the loaded document was never read: {labels}"
    assert any("EditText" in e.class_name for e in settled.elements), "the form fields are still missing"


def test_a_settled_native_screen_is_not_re_read():
    # The extra read costs a dump; only a hybrid screen earns it unconditionally.
    from framework.crawler.app_crawler import AppCrawler

    driver = _LateWebView()
    native = parse_screen(_page(_node("A", (0, 0, 100, 40), "id/a"), _node("B", (0, 50, 100, 90), "id/b")))
    assert AppCrawler(driver, _APP)._await_content(native) is native
