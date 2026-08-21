"""Detect the app(s) in a project dir (device-free): the 'point at your project'
foundation. A repo can hold several apps (Android + iOS, or a monorepo), so detection
returns a list; the config is derived, not hand-typed."""

from framework.devices.project_scan import detect_apps


def _android_module(root, module, application_id=None, manifest_package="com.x.app", with_apk=False):
    m = root / module / "src" / "main"
    m.mkdir(parents=True)
    (m / "AndroidManifest.xml").write_text(
        f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{manifest_package}"/>',
        encoding="utf-8",
    )
    if application_id:
        (root / module / "build.gradle.kts").write_text(
            f'android {{ defaultConfig {{ applicationId = "{application_id}" }} }}'
        )
    if with_apk:
        out = root / module / "build" / "outputs" / "apk" / "debug"
        out.mkdir(parents=True)
        (out / "app-debug.apk").write_text("apk")


def _ios_project(root, name, bundle_id):
    proj = root / name / f"{name}.xcodeproj"
    proj.mkdir(parents=True)
    (proj / "project.pbxproj").write_text(f"PRODUCT_BUNDLE_IDENTIFIER = {bundle_id};", encoding="utf-8")


def test_android_prefers_gradle_application_id_over_manifest(tmp_path):
    _android_module(tmp_path, "app", application_id="com.acme.prod", manifest_package="com.acme")
    apps = detect_apps(str(tmp_path))
    assert apps == [
        {"platform": "android", "package": "com.acme.prod", "source": str(tmp_path / "app"), "build_path": None}
    ]


def test_android_falls_back_to_manifest_package(tmp_path):
    _android_module(tmp_path, "app", application_id=None, manifest_package="com.acme.app")
    apps = detect_apps(str(tmp_path))
    assert len(apps) == 1 and apps[0]["package"] == "com.acme.app"


def test_android_reports_a_built_apk(tmp_path):
    _android_module(tmp_path, "app", application_id="com.acme.app", with_apk=True)
    apps = detect_apps(str(tmp_path))
    assert apps[0]["build_path"].endswith("app-debug.apk")


def test_ios_bundle_id_from_pbxproj(tmp_path):
    _ios_project(tmp_path, "MyApp", "com.acme.MyApp")
    apps = detect_apps(str(tmp_path))
    assert apps == [
        {"platform": "ios", "package": "com.acme.MyApp", "source": str(tmp_path / "MyApp"), "build_path": None}
    ]


def test_ios_skips_unresolved_variable_bundle_id(tmp_path):
    proj = tmp_path / "MyApp" / "MyApp.xcodeproj"
    proj.mkdir(parents=True)
    (proj / "project.pbxproj").write_text("PRODUCT_BUNDLE_IDENTIFIER = $(PRODUCT_BUNDLE_IDENTIFIER);")
    assert detect_apps(str(tmp_path)) == []


def test_monorepo_finds_both_android_and_ios(tmp_path):
    _android_module(tmp_path, "android", application_id="com.acme.android")
    _ios_project(tmp_path, "iosapp", "com.acme.ios")
    apps = detect_apps(str(tmp_path))
    platforms = {a["platform"] for a in apps}
    assert platforms == {"android", "ios"} and len(apps) == 2


def test_build_dir_manifests_are_skipped(tmp_path):
    # a processed manifest under build/ must not be reported as a second app
    _android_module(tmp_path, "app", application_id="com.acme.app")
    stale = tmp_path / "app" / "build" / "intermediates" / "merged_manifests"
    stale.mkdir(parents=True)
    (stale / "AndroidManifest.xml").write_text('<manifest package="com.acme.app"/>')
    apps = detect_apps(str(tmp_path))
    assert len(apps) == 1


def test_missing_or_empty_dir_is_empty(tmp_path):
    assert detect_apps(str(tmp_path / "nope")) == []
    assert detect_apps(str(tmp_path)) == []


def test_daemon_rpc_returns_apps(tmp_path):
    from framework.cli.daemon_commands import JSONRPCServer

    _android_module(tmp_path, "app", application_id="com.acme.app")
    result = JSONRPCServer().handle_project_detect({"path": str(tmp_path)})
    assert result["apps"][0]["package"] == "com.acme.app"
