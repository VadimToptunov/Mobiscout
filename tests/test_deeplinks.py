"""Deeplink discovery: parse the URIs an app declares (iOS Info.plist schemes,
Android browsable VIEW intent-filters) so the crawler can list — and open — the
shortcuts a tap-walk may never reach. Also covers the explicit-config sources
(a ``deeplinks`` list, or an explicit manifest/plist path) folded in alongside
the discovered ones — and, below, the pipeline seeding that turns those URIs into
extra crawl roots and merges what they find back into the result."""

import plistlib

import framework.crawler.deeplinks as dl
import framework.crawler.pipeline as pipeline
from framework.crawler.app_crawler import parse_screen


def test_ios_plist_schemes_ignore_http():
    plist = plistlib.dumps(
        {"CFBundleURLTypes": [{"CFBundleURLSchemes": ["chaosbank", "cbank"]}, {"CFBundleURLSchemes": ["https"]}]}
    )
    assert dl.deeplinks_from_ios_plist(plist) == ["cbank://", "chaosbank://"]


def test_ios_plist_malformed_is_empty():
    assert dl.deeplinks_from_ios_plist(b"not a plist") == []


_MANIFEST = """<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.acme.app">
  <application><activity>
    <intent-filter>
      <action android:name="android.intent.action.VIEW"/>
      <category android:name="android.intent.category.BROWSABLE"/>
      <data android:scheme="chaosbank" android:host="open" android:pathPrefix="/trip"/>
    </intent-filter>
    <intent-filter>
      <action android:name="android.intent.action.VIEW"/>
      <category android:name="android.intent.category.BROWSABLE"/>
      <data android:scheme="https" android:host="app.acme.com"/>
    </intent-filter>
    <intent-filter>
      <action android:name="android.intent.action.MAIN"/>
    </intent-filter>
  </activity></application>
</manifest>"""


def test_android_manifest_browsable_view_only():
    # custom scheme kept, https app-link and non-browsable filter dropped
    assert dl.deeplinks_from_android_manifest(_MANIFEST) == ["chaosbank://open/trip"]


def test_android_manifest_malformed_is_empty():
    assert dl.deeplinks_from_android_manifest("<broken") == []


def test_extract_deeplinks_android_from_source_dir(tmp_path):
    manifest = tmp_path / "src" / "main" / "AndroidManifest.xml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(_MANIFEST, encoding="utf-8")
    got = dl.extract_deeplinks({"platform": "android", "package": "com.acme.app", "source": str(tmp_path)})
    assert got == ["chaosbank://open/trip"]


def test_extract_deeplinks_ios_from_plist(monkeypatch):
    plist = plistlib.dumps({"CFBundleURLTypes": [{"CFBundleURLSchemes": ["cbank"]}]})
    monkeypatch.setattr(dl, "_ios_app_plist", lambda config: plist)
    assert dl.extract_deeplinks({"platform": "ios", "udid": "x", "package": "com.acme"}) == ["cbank://"]


def test_extract_deeplinks_never_raises_without_source():
    assert dl.extract_deeplinks({"platform": "android", "package": "com.x"}) == []


def test_extract_deeplinks_includes_explicit_list():
    # An explicit ``deeplinks`` config list is always folded in (and merged with
    # any discovered ones), deduped and sorted.
    got = dl.extract_deeplinks({"platform": "android", "package": "com.x", "deeplinks": ["myapp://home", "myapp://a"]})
    assert got == ["myapp://a", "myapp://home"]


def test_extract_deeplinks_from_explicit_manifest_path(tmp_path):
    # An explicit ``android_manifest`` path is read directly (no source-dir walk).
    p = tmp_path / "AndroidManifest.xml"
    p.write_text(_MANIFEST, encoding="utf-8")
    got = dl.extract_deeplinks({"platform": "android", "package": "com.acme.app", "android_manifest": str(p)})
    assert got == ["chaosbank://open/trip"]


def test_markdown_lists_uris_and_empty_case():
    assert "No browsable deeplinks" in dl.deeplinks_markdown([], "com.x")
    md = dl.deeplinks_markdown(["cbank://open"], "com.x")
    assert "cbank://open" in md and "simctl openurl" in md


# --- seeding a crawl from those URIs ------------------------------------------
# The parsers above only produce a list of strings. What makes deeplinks *coverage*
# is the pipeline opening each one as an extra crawl root and folding what it finds
# back into the main result — so these drive run_kit/_crawl with a driver that can
# open URLs, which is what every other test in the suite lacks.

_APP = "com.acme.app"


def _n(text, bounds, cls="android.widget.Button", clickable=True, rid=""):
    # `rid` matters: the screen fingerprint is structural and ignores text, so nodes that
    # differ only in their label collapse to ONE fingerprint. Without distinct ids the
    # seven screens below became three, and the seeding assertions could not fail.
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="{cls}" resource-id="{rid}" text="{text}" content-desc="" '
        f'clickable="{"true" if clickable else "false"}" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _xml(*nodes):
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


# Only "home" and "help" are reachable by tapping; everything else needs a deeplink.
_SEED_SCREENS = {
    "home": _xml(_n("Help", (0, 0, 100, 50), rid="id/home_help")),
    "help": _xml(_n("Support hours", (0, 0, 100, 50), clickable=False, rid="id/help_hours")),
    "trip": _xml(_n("Trip detail", (0, 0, 100, 50), rid="id/trip_open_detail")),
    "trip_detail": _xml(_n("Departure gate B12", (0, 0, 100, 50), clickable=False, rid="id/trip_detail_gate")),
    "offers": _xml(_n("Current offers", (0, 0, 100, 50), clickable=False, rid="id/offers_list")),
    "gate": _xml(
        _n("user", (0, 0, 200, 40), cls="android.widget.EditText", rid="id/gate_user"),
        _n("Log in", (0, 50, 100, 90), rid="id/gate_submit"),
    ),
    "vault": _xml(_n("Your documents", (0, 0, 200, 40), clickable=False, rid="id/vault_docs")),
}
_SEED_NAV = {("home", "Help"): "help", ("trip", "Trip detail"): "trip_detail", ("gate", "Log in"): "vault"}


class _SeedDriver:
    """Fake app + deeplink handler. ``handled`` maps a URI to the screen it opens;
    a URI that is absent opens a browser instead — reported as False, like the real
    adb/iOS drivers do."""

    def __init__(self, handled):
        self.handled = handled
        self.current = "home"
        self.nav = []
        self.opened = []

    def page_source(self):
        return _SEED_SCREENS[self.current]

    def current_package(self):
        return _APP

    def back(self):
        if self.nav:
            self.current = self.nav.pop()

    def type_text(self, text):
        pass

    def tap(self, x, y):
        label = ""
        for e in parse_screen(self.page_source()).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                label = e.label
                break
        target = _SEED_NAV.get((self.current, label))
        if target:
            self.nav.append(self.current)
            self.current = target

    def open_url(self, uri, package=None, tries=6):
        self.opened.append(uri)
        target = self.handled.get(uri)
        if not target:
            return False
        self.nav = []
        self.current = target
        return True


def _fp(name):
    return parse_screen(_SEED_SCREENS[name]).fingerprint


def _crawl(deeplinks, handled, **config):
    driver = _SeedDriver(handled)
    cfg = {"package": _APP, "max_steps": 60, "deeplinks": deeplinks, **config}
    return pipeline._crawl(cfg, driver=driver), driver


def test_a_tap_walk_alone_reaches_neither_seed_screen():
    # The baseline the two tests below are measured against: without seeding, the
    # deeplink-only screens simply do not exist in the result.
    result, _ = _crawl([], {})
    assert set(result.screens) == {_fp("home"), _fp("help")}


def test_deeplink_seeds_add_the_screens_and_their_transitions():
    result, driver = _crawl(
        ["myapp://offers", "myapp://trip"],
        {"myapp://trip": "trip", "myapp://offers": "offers"},
    )
    assert driver.opened == ["myapp://offers", "myapp://trip"]  # sorted by extract_deeplinks
    assert {_fp("trip"), _fp("trip_detail"), _fp("offers")} <= set(result.screens)
    # The seed's own transition survives the merge, with both endpoints mapped —
    # otherwise build_graph drops the edge and the seeded screen is unreachable.
    edge = [(s, d) for s, el, d in result.transitions if el.label == "Trip detail"]
    assert edge == [(_fp("trip"), _fp("trip_detail"))]


def test_two_seeds_landing_on_one_screen_do_not_duplicate_its_transitions():
    result, _ = _crawl(
        ["myapp://trip", "myapp://trip/latest"],
        {"myapp://trip": "trip", "myapp://trip/latest": "trip"},
    )
    assert len([1 for _, el, _ in result.transitions if el.label == "Trip detail"]) == 1


def test_a_seed_that_opens_a_browser_is_skipped():
    result, driver = _crawl(["myapp://offers", "https://acme.com/promo"], {"myapp://offers": "offers"})
    assert "https://acme.com/promo" in driver.opened  # it was tried...
    assert _fp("offers") in result.screens  # ...the handled one still seeded
    assert set(result.screens) == {_fp("home"), _fp("help"), _fp("offers")}


def test_a_gate_a_seed_crawl_passed_keeps_its_screens_tagged_behind_auth():
    # A seed can land on a login of its own. Losing what it learned would leave the
    # screens behind that gate untagged — and codegen emits those without the auth
    # prefix, i.e. red.
    result, _ = _crawl(
        ["myapp://vault"],
        {"myapp://vault": "gate"},
        waypoints=[
            {"when": {"has_input": True}, "action": "fill", "data": {"fields": {"user": "demo"}, "submit": "log in"}}
        ],
    )
    assert _fp("vault") in result.screens
    assert _fp("vault") in result.gated
    assert result.auth_sequence  # the gate the seed passed is carried over for codegen
