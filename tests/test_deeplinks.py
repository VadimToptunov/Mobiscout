"""Deeplink discovery: parse the URIs an app declares (iOS Info.plist schemes,
Android browsable VIEW intent-filters) so the crawler can list — and open — the
shortcuts a tap-walk may never reach. Also covers the explicit-config sources
(a ``deeplinks`` list, or an explicit manifest/plist path) folded in alongside
the discovered ones."""

import plistlib

import framework.crawler.deeplinks as dl


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
