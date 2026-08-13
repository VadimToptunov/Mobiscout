"""Deeplink seeding (device-free): extraction from manifest/plist, config merge,
result merge, and the pipeline opening a seed + folding its screens in."""

from framework.crawler.app_crawler import parse_screen
from framework.crawler.deeplinks import (
    deeplinks_from_android_manifest,
    deeplinks_from_ios_plist,
    extract_deeplinks,
)
from framework.crawler.models import CrawlResult
from framework.crawler.pipeline import _merge_results, _seed_deeplinks

APP = "com.example.app"

_MANIFEST = """<?xml version="1.0"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.app">
  <application>
    <activity android:name=".Deep">
      <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW"/>
        <category android:name="android.intent.category.DEFAULT"/>
        <category android:name="android.intent.category.BROWSABLE"/>
        <data android:scheme="https" android:host="example.com" android:pathPrefix="/app"/>
      </intent-filter>
      <intent-filter>
        <action android:name="android.intent.action.VIEW"/>
        <category android:name="android.intent.category.BROWSABLE"/>
        <data android:scheme="myapp" android:host="promo"/>
      </intent-filter>
    </activity>
    <activity android:name=".Internal">
      <intent-filter>
        <action android:name="android.intent.action.VIEW"/>
        <data android:scheme="internal" android:host="secret"/>
      </intent-filter>
    </activity>
  </application>
</manifest>"""


def test_android_manifest_browsable_deeplinks_only():
    uris = deeplinks_from_android_manifest(_MANIFEST)
    assert "https://example.com/app" in uris
    assert "myapp://promo" in uris
    # The non-browsable VIEW filter (.Internal) is an internal intent, not a deeplink.
    assert all("internal" not in u for u in uris)


def test_ios_plist_url_schemes():
    plist = {"CFBundleURLTypes": [{"CFBundleURLSchemes": ["myapp", "myapp-dev"]}, {"CFBundleURLSchemes": ["other"]}]}
    assert deeplinks_from_ios_plist(plist) == ["myapp://", "myapp-dev://", "other://"]


def test_extract_deeplinks_explicit_list_first_and_deduped():
    config = {"deeplinks": ["myapp://home", "myapp://home", "myapp://cart"]}
    assert extract_deeplinks(config) == ["myapp://home", "myapp://cart"]


def test_merge_results_unions_screens_and_transitions():
    a = CrawlResult(screens={"h": parse_screen("<hierarchy/>")}, transitions=[], steps=2)
    b = CrawlResult(screens={"p": parse_screen("<hierarchy/>")}, transitions=[], steps=3)
    merged = _merge_results(a, b)
    assert set(merged.screens) == {"h", "p"}
    assert merged.steps == 5


def _promo_screen():
    return (
        '<hierarchy rotation="0">'
        '<node class="android.widget.Button" resource-id="id/buy" text="Buy" content-desc="" '
        'clickable="true" bounds="[0,0][100,50]"/></hierarchy>'
    )


class _SeedDriver:
    """A deeplink-only screen: unreachable by tapping, reached via open_url."""

    def __init__(self):
        self.opened = []

    def open_url(self, uri, package=None):
        self.opened.append((uri, package))
        return True

    def page_source(self):
        return _promo_screen()

    def current_package(self):
        return APP

    def back(self):
        pass

    def tap(self, x, y):
        pass


def test_seed_deeplinks_opens_and_merges():
    driver = _SeedDriver()
    config = {"package": APP, "deeplinks": ["myapp://promo"], "seed_max_steps": 4, "seed_max_seconds": 5}
    result = CrawlResult(screens={"home": parse_screen("<hierarchy/>")}, transitions=[], steps=0)
    merged = _seed_deeplinks(config, driver, result, [])
    # The deeplink was opened (scoped to the app under test)...
    assert driver.opened == [("myapp://promo", APP)]
    # ...and the promo screen it reached is now in the map alongside home.
    blobs = [" ".join(e.label for e in s.elements).lower() for s in merged.screens.values()]
    assert any("buy" in b for b in blobs)


def test_seed_deeplinks_noop_without_open_url():
    # A driver lacking open_url (e.g. a minimal stub) must not break seeding.
    class _NoUrl:
        def page_source(self):
            return "<hierarchy/>"

    result = CrawlResult(screens={"home": parse_screen("<hierarchy/>")}, transitions=[], steps=0)
    out = _seed_deeplinks({"package": APP, "deeplinks": ["myapp://x"]}, _NoUrl(), result, [])
    assert set(out.screens) == {"home"}
