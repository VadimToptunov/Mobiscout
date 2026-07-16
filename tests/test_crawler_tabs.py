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
# A pushed detail (reached from Markets → EUR); no tab bar, Back pops it.
_DETAIL = {"eur_detail": [_el("StaticText", "EUR/USD", 0, 60), _el("Button", "Confirm", 0, 120)]}


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
        self.visited = {"home"}

    def _elements(self):
        # (name, cx, cy) for every hittable control on the current screen.
        out = []
        for itype, name, x in _TABS if self.current in _SECTIONS else []:
            out.append((name, x + 50, 820))
        for src in _SECTIONS.get(self.current) or _DETAIL.get(self.current) or []:
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
        return _page(self.current)

    def tap(self, x, y):
        name = self._hit(x, y)
        if name in {"Home", "Markets", "Portfolio", "Card"}:
            self.current, self._pushed = name.lower(), False
        elif name == "EUR" and self.current == "markets":
            self.current, self._pushed = "eur_detail", True

    def back(self):
        # iOS edge-swipe: pops a pushed detail, but on a tab root does nothing.
        if self._pushed:
            self.current, self._pushed = "markets", False

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
