"""Salvaged from PRs #337 / #338 (device-free):

* fingerprint hygiene — a feed whose rows differ only by volatile counts/prices
  in ``content-desc`` dedupes to one screen instead of forking endlessly;
* plateau / novelty stop — a crawl ends once coverage saturates (no new screen
  template for ``max_novelty_gap`` steps), a new screen re-anchors it, and it is
  disabled at 0; and
* submit disambiguation — a login gate that repeats the same label above and
  inside the form submits the *form's* button (below the inputs), not the
  same-labelled welcome button.
"""

from framework.crawler.app_crawler import AppCrawler
from framework.crawler.models import CrawlResult
from framework.crawler.parse import parse_screen
from framework.crawler.waypoints import _submit_button

# --- fingerprint hygiene ---------------------------------------------------------


def _feed(desc, rid=""):
    return parse_screen(
        '<hierarchy rotation="0">'
        f'<node class="android.widget.TextView" resource-id="{rid}" text="" '
        f'content-desc="{desc}" clickable="true" bounds="[0,0][300,60]"/>'
        "</hierarchy>"
    )


def test_feed_rows_with_volatile_counts_dedupe_to_one_screen():
    # No resource-id to key on -> content-desc feeds the fingerprint, but digits
    # are blanked, so the same row with different counts is the same screen.
    assert _feed("Post by Alice, 3 likes").fingerprint == _feed("Post by Alice, 42 likes").fingerprint


def test_content_desc_dropped_when_resource_id_present():
    # With an id to key on, volatile content-desc is ignored entirely.
    assert _feed("Alice", rid="id/row").fingerprint == _feed("Bob", rid="id/row").fingerprint


def test_structurally_different_screens_still_differ():
    two = parse_screen(
        '<hierarchy rotation="0">'
        '<node class="android.widget.TextView" resource-id="" text="" content-desc="Home" '
        'clickable="true" bounds="[0,0][300,60]"/>'
        '<node class="android.widget.Button" resource-id="" text="" content-desc="Pay" '
        'clickable="true" bounds="[0,60][300,120]"/>'
        "</hierarchy>"
    )
    assert two.fingerprint != _feed("Home").fingerprint


# --- plateau / novelty stop ------------------------------------------------------


def _crawler(**kw):
    return AppCrawler(object(), "com.example.app", max_steps=1000, **kw)


def _result(n_screens, steps):
    r = CrawlResult(steps=steps)
    for i in range(n_screens):
        r.screens[str(i)] = None
    return r


def test_plateau_stops_after_gap_without_new_screens():
    c = _crawler(max_novelty_gap=5)
    assert c._within_budget(_result(1, 0)) is True  # anchors the plateau at step 0
    assert c._within_budget(_result(1, 4)) is True  # gap 4 < 5, keep going
    assert c._within_budget(_result(1, 5)) is False  # gap hit 5 -> stop


def test_new_screen_reanchors_the_plateau():
    c = _crawler(max_novelty_gap=5)
    assert c._within_budget(_result(1, 4)) is True
    assert c._within_budget(_result(2, 8)) is True  # a 2nd screen at step 8 re-anchors
    assert c._within_budget(_result(2, 13)) is False  # 13 - 8 == gap -> stop


def test_plateau_disabled_at_zero():
    c = _crawler(max_novelty_gap=0)
    assert c._within_budget(_result(1, 900)) is True  # never plateau-stops


# --- submit disambiguation -------------------------------------------------------


def _btn(text, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.Button" resource-id="" text="{text}" content-desc="" '
        f'clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _edit(text, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.EditText" resource-id="" text="{text}" content-desc="" '
        f'clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _screen(*nodes):
    return parse_screen('<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>").elements


def test_submit_prefers_form_button_below_inputs():
    els = _screen(
        _btn("Log in", (0, 0, 300, 40)),  # welcome button, ABOVE the inputs
        _edit("Username", (0, 100, 300, 140)),
        _edit("Password", (0, 150, 300, 190)),
        _btn("Log in", (0, 220, 300, 260)),  # the form's own submit, BELOW the inputs
    )
    inputs = [e for e in els if e.class_name.endswith("EditText")]
    chosen = _submit_button(els, "log in", inputs)
    assert chosen is not None and chosen.bounds[1] == 220  # the form submit, not the welcome button


def test_submit_falls_back_to_lowest_when_none_below():
    els = _screen(_btn("Go", (0, 0, 300, 40)), _btn("Go", (0, 300, 300, 340)))
    chosen = _submit_button(els, "go", [])  # no filled inputs -> lowest match
    assert chosen is not None and chosen.bounds[1] == 300


def test_submit_none_when_no_match():
    els = _screen(_btn("Cancel", (0, 0, 300, 40)))
    assert _submit_button(els, "log in", []) is None
