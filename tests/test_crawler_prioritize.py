"""Unit tests for smart tap-ordering (`_prioritize` / `_own_interactive`).

The crawl must explore by semantic value — navigation and primary actions first,
decoration last — and must not tap every one of twenty identical list rows. These
pin that ordering and the sibling cap so the crawl stops "poking wherever".
"""

from framework.crawler.app_crawler import AppCrawler, _SIBLING_CAP
from framework.crawler.models import CrawlElement, CrawlScreen

APP = "com.example.app"


class _NullDriver:
    def current_package(self):
        return APP


def _crawler():
    return AppCrawler(_NullDriver(), APP)


def _el(rid, cls, bounds, text=""):
    return CrawlElement(
        resource_id=rid,
        text=text,
        content_desc="",
        class_name=cls,
        clickable=True,
        bounds=bounds,
        package="",
    )


def _row(i):
    # A column of identically shaped list rows: same x/width/height, stepping down.
    y = 200 + i * 60
    return _el(f"id/row{i}", "android.widget.LinearLayout", (0, y, 300, y + 55), text=f"Row {i}")


def test_buttons_ranked_before_images():
    img = _el("id/icon", "android.widget.ImageView", (0, 0, 40, 40))
    btn = _el("id/go", "android.widget.Button", (0, 100, 200, 150), text="Go")
    screen = CrawlScreen(fingerprint="fp", elements=[img, btn])
    ordered = list(_crawler()._own_interactive(screen))
    assert ordered[0].resource_id == "id/go"  # button before the decorative icon


def test_identical_list_rows_are_capped():
    rows = [_row(i) for i in range(20)]
    screen = CrawlScreen(fingerprint="fp", elements=rows)
    ordered = list(_crawler()._own_interactive(screen))
    # Twenty identical rows collapse to at most the cap — not all twenty.
    assert len(ordered) == _SIBLING_CAP
    assert _SIBLING_CAP < 20


def test_distinct_controls_are_not_capped():
    # Same role but genuinely different shapes/columns -> not siblings, all kept.
    a = _el("id/a", "android.widget.Button", (0, 0, 100, 50), text="A")
    b = _el("id/b", "android.widget.Button", (150, 0, 400, 90), text="B")
    c = _el("id/c", "android.widget.Button", (0, 200, 300, 260), text="C")
    screen = CrawlScreen(fingerprint="fp", elements=[a, b, c])
    ordered = list(_crawler()._own_interactive(screen))
    assert len(ordered) == 3


def test_primary_nav_leads_and_is_never_capped():
    # A five-entry bottom tab bar: identically shaped, but each opens a section,
    # so none may be dropped and all must lead the queue.
    bottom = 800
    tabs = [_el(f"id/tab{i}", "Tab", (i * 80, bottom - 40, i * 80 + 70, bottom), text=f"T{i}") for i in range(5)]
    content = _el("id/body", "android.widget.Button", (0, 100, 300, 150), text="Body")
    screen = CrawlScreen(fingerprint="fp", elements=tabs + [content], platform="ios")
    ordered = list(_crawler()._own_interactive(screen))
    lead = ordered[: len(tabs)]
    assert all(e.class_name == "Tab" for e in lead)  # nav leads
    assert sum(1 for e in ordered if e.class_name == "Tab") == 5  # none capped


def test_exclude_nav_drops_the_bar():
    bottom = 800
    tabs = [_el(f"id/tab{i}", "Tab", (i * 80, bottom - 40, i * 80 + 70, bottom), text=f"T{i}") for i in range(5)]
    content = _el("id/body", "android.widget.Button", (0, 100, 300, 150), text="Body")
    screen = CrawlScreen(fingerprint="fp", elements=tabs + [content], platform="ios")
    ordered = list(_crawler()._own_interactive(screen, exclude_nav=True))
    assert all(e.class_name != "Tab" for e in ordered)
    assert [e.resource_id for e in ordered] == ["id/body"]
