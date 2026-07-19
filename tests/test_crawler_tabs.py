"""A tab-based app is the case a naive depth-first crawl gets wrong: it burns its
step budget deep inside the first tab and never reaches the others, and on iOS
Back is an edge-swipe that pops a pushed screen but does *not* switch tabs. The
crawler must recognise the persistent bottom bar and drive each section from its
tab. These tests pin that with a fake driver modelling exactly that app shape."""

from framework.crawler.app_crawler import AppCrawler

WIDTH, HEIGHT = 400, 850
_BUNDLE = "com.example.tabapp"

# Bottom tab bar shared by every top-level section (x-slots of 100px, y≈820).
_TABS = [
    ("Button", "Home", 0),
    ("Button", "Markets", 100),
    ("Button", "Portfolio", 200),
    ("Button", "Card", 300),
]


def _el(itype, name, x, y, w=100, h=40):
    return (
        f'<XCUIElementType{itype} type="XCUIElementType{itype}" name="{name}" '
        f'label="{name}" x="{x}" y="{y}" width="{w}" height="{h}" '
        f'visible="true" enabled="true"/>'
    )


def _tabbar():
    return "".join(_el(t, n, x, 800) for t, n, x in _TABS)


# Each top-level section: distinct content buttons on top + the shared tab bar,
# so the four tabs get four distinct structural fingerprints.
_SECTIONS = {
    "home": [_el("Button", "Transfer", 0, 100), _el("Button", "Exchange", 0, 160)],
    "markets": [_el("Button", "EUR", 0, 100), _el("Button", "GBP", 0, 160)],
    "portfolio": [_el("Button", "Sort", 0, 100)],
    "card": [_el("Button", "Freeze", 0, 100)],
}
# Pushed details (no tab bar, Back pops them): eur_detail from Markets→EUR, and
# transactions from a Home "See all" link that only exists once Home is scrolled.
_DETAIL = {
    "eur_detail": [_el("StaticText", "EUR/USD", 0, 60), _el("Button", "Confirm", 0, 120)],
    "transactions": [_el("StaticText", "History", 0, 60), _el("Button", "Filter", 0, 120)],
    # A modal sheet (opened by Home → Exchange): its "Detail" control does not
    # dismiss it, and Back (edge-swipe) can't either — only a swipe-down does.
    "exchange_sheet": [_el("StaticText", "ExchangeTitle", 0, 60), _el("Button", "Detail", 0, 120)],
}
# Below-the-fold link on Home — invisible until the crawler scrolls down. Mid
# content (not the bottom strip), so it reads as a link, not a tab.
_SEE_ALL = _el("Button", "SeeAll", 0, 450)


def _page(screen):
    body = "".join(_SECTIONS.get(screen, _DETAIL.get(screen, [])))
    if screen in _SECTIONS:  # tab roots carry the persistent bar
        body += _tabbar()
    return f'<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="TabApp">{body}</XCUIElementTypeApplication>'


class FakeTabDriver:
    """A four-tab iOS app. Tapping a tab switches sections; Back only pops a
    pushed detail (never switches tabs — the real iOS behaviour)."""

    def __init__(self):
        self.current = "home"
        self._pushed = False  # on a detail pushed above a tab root
        self._modal = False  # on a modal sheet (Back can't dismiss it)
        self._scrolled = False  # Home scrolled far enough to reveal "See all"
        self._txn_loaded = False  # Transactions finished its async .task load
        self.visited = {"home"}

    def _sources(self):
        if self.current == "transactions" and not self._txn_loaded:
            return [_el("StaticText", "Loading", 0, 60)]  # async skeleton, no content yet
        srcs = list(_SECTIONS.get(self.current) or _DETAIL.get(self.current) or [])
        if self.current == "home" and self._scrolled:
            srcs.append(_SEE_ALL)  # below-the-fold, only after a scroll
        return srcs

    def _elements(self):
        # (name, cx, cy) for every hittable control on the current screen.
        out = []
        for itype, name, x in _TABS if self.current in _SECTIONS else []:
            out.append((name, x + 50, 820))
        for src in self._sources():
            name = src.split('name="', 1)[1].split('"', 1)[0]
            x = int(src.split('x="', 1)[1].split('"', 1)[0])
            y = int(src.split('y="', 1)[1].split('"', 1)[0])
            out.append((name, x + 50, y + 20))
        return out

    def _hit(self, tx, ty):
        for name, cx, cy in self._elements():
            if abs(cx - tx) <= 50 and abs(cy - ty) <= 20:
                return name
        return None

    def page_source(self):
        self.visited.add(self.current)
        body = "".join(self._sources())
        if self.current in _SECTIONS:  # tab roots carry the persistent bar
            body += _tabbar()
        return f'<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="TabApp">{body}</XCUIElementTypeApplication>'

    def tap(self, x, y):
        name = self._hit(x, y)
        if name in {"Home", "Markets", "Portfolio", "Card"}:
            self.current, self._pushed, self._modal, self._scrolled = name.lower(), False, False, False
        elif name == "EUR" and self.current == "markets":
            self.current, self._pushed = "eur_detail", True
        elif name == "SeeAll" and self.current == "home":
            self.current, self._pushed, self._txn_loaded = "transactions", True, False
        elif name == "Exchange" and self.current == "home":
            self.current, self._modal = "exchange_sheet", True  # a sheet Back can't close

    def scroll(self, direction="down"):
        if self.current == "home" and direction == "down":
            self._scrolled = True
        elif self._modal and direction == "up":  # swipe-down dismisses the sheet
            self.current, self._modal = "home", False

    def refresh(self, wait=0):
        # A second look: Transactions finishes loading its content.
        if self.current == "transactions":
            self._txn_loaded = True
        return self.page_source()

    def back(self):
        # iOS edge-swipe: pops a pushed detail, but neither a modal sheet nor a
        # tab root responds to it.
        if self._modal:
            return
        if self._pushed:
            self.current, self._pushed = ("markets" if self.current == "eur_detail" else "home"), False

    def current_package(self):
        return _BUNDLE


def test_crawler_visits_every_tab_not_just_the_first():
    driver = FakeTabDriver()
    result = AppCrawler(driver, _BUNDLE, max_steps=60, max_depth=8).crawl()
    # All four sections *and* the pushed detail behind Markets get discovered —
    # a naive DFS would stall inside Home and miss Markets/Portfolio/Card.
    assert {"home", "markets", "portfolio", "card", "eur_detail"} <= driver.visited
    # Four structurally distinct tab roots + the detail => at least five screens.
    assert len(result.screens) >= 5


def test_scrolling_reveals_below_the_fold_links():
    """A "See all" link that only exists once Home is scrolled must still be
    found and followed — off-screen content is the #1 thing a tap-only crawl
    misses. Without scroll support the Transactions screen is unreachable."""
    driver = FakeTabDriver()
    result = AppCrawler(driver, _BUNDLE, max_steps=80, max_depth=8).crawl()
    assert "transactions" in driver.visited


def test_recovers_from_a_modal_sheet_back_cannot_dismiss():
    """Opening a sheet that ignores Back must not strand the crawl: it has to
    dismiss the sheet and carry on, or every later tap lands on the wrong screen.
    Proof: the below-the-fold Transactions link, tapped only *after* the Exchange
    sheet is opened and dismissed, is still reached."""
    driver = FakeTabDriver()
    result = AppCrawler(driver, _BUNDLE, max_steps=120, max_depth=8).crawl()
    assert "exchange_sheet" in driver.visited  # we did open it
    assert "transactions" in driver.visited  # and still got past it to later work


def test_async_screen_content_is_captured_not_the_blank_skeleton():
    """A screen that lands empty and fills in via an async load (SwiftUI `.task`)
    must be re-read so its real content is mapped, not the loading skeleton. The
    Transactions screen only exposes its "Filter" control once loaded."""
    driver = FakeTabDriver()
    result = AppCrawler(driver, _BUNDLE, max_steps=120, max_depth=8).crawl()
    loaded = any(e.content_desc == "Filter" for screen in result.screens.values() for e in screen.elements)
    assert loaded, "async-loaded Transactions content (Filter) was not captured"


def test_all_tab_roots_mapped_even_on_a_tight_step_budget():
    """Breadth first: every section root is registered before any deep dive, so a
    crawl that runs out of steps still maps the whole top level rather than one
    tab's guts. A single-pass DFS would spend the budget inside Markets."""
    driver = FakeTabDriver()
    result = AppCrawler(driver, _BUNDLE, max_steps=5, max_depth=8).crawl()
    assert {"home", "markets", "portfolio", "card"} <= driver.visited
    assert len(result.screens) >= 4


def test_single_root_app_still_crawls_without_a_nav_bar():
    """No bottom bar (<2 nav items) -> the plain depth-first path, unchanged."""

    bare = (
        '<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="App">'
        + _el("Button", "Only", 0, 100)  # one control, no bottom bar
        + "</XCUIElementTypeApplication>"
    )

    class OneScreen:
        def page_source(self):
            return bare

        def tap(self, x, y):
            pass

        def back(self):
            pass

        def current_package(self):
            return _BUNDLE

    result = AppCrawler(OneScreen(), _BUNDLE, max_steps=10).crawl()
    assert len(result.screens) == 1
