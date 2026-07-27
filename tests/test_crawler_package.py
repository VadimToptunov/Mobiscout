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


def test_ios_springboard_element_is_marked_foreign_and_excluded():
    # A permission alert / springboard control is owned by a *different* iOS app
    # (SpringBoard). Before the fix every iOS element had package="" so _own was
    # True for all of them and the crawler would tap the system dialog. Now the AUT
    # keeps package="" (own) while the springboard subtree is tagged foreign.
    xml = (
        "<AppiumAUT>"
        '<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="MyApp" '
        'x="0" y="0" width="390" height="844">'
        '<XCUIElementTypeButton type="XCUIElementTypeButton" name="app_ok" label="Continue" '
        'x="20" y="100" width="200" height="44"/>'
        "</XCUIElementTypeApplication>"
        '<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="SpringBoard" '
        'x="0" y="0" width="390" height="844">'
        '<XCUIElementTypeButton type="XCUIElementTypeButton" name="Allow" label="Allow" '
        'x="20" y="400" width="200" height="44"/>'
        "</XCUIElementTypeApplication>"
        "</AppiumAUT>"
    )
    screen = parse_mod.parse_screen(xml)
    assert screen.platform == "ios"
    by_name = {e.content_desc: e for e in screen.elements}
    assert by_name["app_ok"].package == ""  # app under test -> owned
    assert by_name["Allow"].package.lower() == "springboard"  # system dialog -> foreign

    crawler = ac_mod.AppCrawler(_NullDriver(), "com.example.myapp")
    assert crawler._own(by_name["app_ok"]) is True
    assert crawler._own(by_name["Allow"]) is False  # never tap the system dialog


class _NullDriver:
    def page_source(self):
        return ""

    def tap(self, x, y):
        pass

    def back(self):
        pass

    def current_package(self):
        return "com.example.myapp"


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
