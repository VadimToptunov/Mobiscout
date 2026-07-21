"""app_crawler.py was decomposed: the value types moved to crawler.models, the
page-source parsing to crawler.parse, leaving the AppCrawler engine. The wide
existing crawler suite already exercises behaviour through the historical import
path (which the split preserves); these just pin the new layout — the granular
modules are importable and app_crawler re-exports the very same objects.
"""

import framework.crawler.app_crawler as ac_mod
import framework.crawler.models as models_mod
import framework.crawler.parse as parse_mod


def test_granular_modules_expose_their_symbols():
    assert models_mod.CrawlerDriver is not None
    assert models_mod.CrawlElement is not None
    assert models_mod.CrawlScreen is not None
    assert models_mod.CrawlResult is not None
    assert parse_mod.parse_screen is not None


def test_app_crawler_reexports_the_same_objects():
    # Historical imports must resolve to the identical objects now living in the
    # granular modules (not copies), so isinstance/identity checks elsewhere hold.
    assert ac_mod.CrawlElement is models_mod.CrawlElement
    assert ac_mod.CrawlScreen is models_mod.CrawlScreen
    assert ac_mod.CrawlResult is models_mod.CrawlResult
    assert ac_mod.CrawlerDriver is models_mod.CrawlerDriver
    assert ac_mod.parse_screen is parse_mod.parse_screen


def test_parse_is_self_contained_and_produces_a_screen():
    xml = (
        '<?xml version="1.0"?><hierarchy rotation="0">'
        '<node class="android.widget.Button" text="Go" content-desc="" '
        'resource-id="" package="com.x" clickable="true" bounds="[0,0][100,50]"/>'
        "</hierarchy>"
    )
    screen = parse_mod.parse_screen(xml)
    assert isinstance(screen, models_mod.CrawlScreen)
    assert len(screen.elements) == 1
    assert screen.elements[0].label == "Go"
    assert screen.fingerprint  # non-empty structural fingerprint
