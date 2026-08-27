"""A screen read the instant after a tap can be mid-transition: the outgoing
screen's controls linger a frame while the incoming screen animates in. If the
crawler fingerprints *that* frame, the kit asserts a control that isn't really on
the destination — e.g. an Omni-Notes "search" test asserting the home screen's
FAB, which it left behind. These pin that the crawler settles before recording.
"""

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


# home --"Search"--> search. The settled search screen has a query field and a
# result, and no FAB. The FAB belongs to home; it lingers one frame into search.
HOME = _screen(
    _node("New", "id/fab", True, (0, 0, 100, 50)),
    _node("Search", "id/search", True, (0, 60, 100, 110)),
)
SEARCH_SETTLED = _screen(
    _node("Query", "id/query", True, (0, 0, 100, 50)),
    _node("A result", "id/result", True, (0, 60, 100, 110)),
)
# The transitional frame: home's FAB still on screen while search's field is in.
SEARCH_TRANSITIONAL = _screen(
    _node("New", "id/fab", True, (0, 0, 100, 50)),
    _node("Query", "id/query", True, (0, 0, 100, 50)),
)


class SettleDriver:
    """Returns the transitional frame on the first read after arriving on search,
    then the settled frame once refresh() has 'waited' for the animation."""

    def __init__(self):
        self.current = "home"
        self.pkg = APP
        self._mid_transition = False

    def page_source(self):
        if self.current == "search":
            return SEARCH_TRANSITIONAL if self._mid_transition else SEARCH_SETTLED
        return HOME

    def refresh(self, wait=1.0):
        # A re-read after a beat: the transition has finished by now.
        self._mid_transition = False
        return self.page_source()

    def current_package(self):
        return self.pkg

    def back(self):
        self.pkg = APP
        self.current = "home"

    def tap(self, x, y):
        for e in parse_screen(self.page_source()).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2 and e.resource_id == "id/search":
                self.current = "search"
                self._mid_transition = True  # a fresh transition begins
                return


def _search_screen(result):
    """The recorded screen that is the search screen (has the query field)."""
    for screen in result.screens.values():
        ids = {e.resource_id for e in screen.elements}
        if "id/query" in ids:
            return screen
    return None


def test_search_screen_is_recorded_without_the_lingering_fab():
    driver = SettleDriver()
    result = AppCrawler(driver, APP, max_steps=50).crawl()
    search = _search_screen(result)
    assert search is not None, "search screen was never recorded"
    ids = {e.resource_id for e in search.elements}
    # The FAB belongs to home. If the crawler fingerprinted the transitional frame,
    # id/fab is here and the kit would assert it on the search screen.
    assert "id/fab" not in ids, f"recorded a transitional frame: {ids}"
    assert "id/query" in ids
