"""Project scaffolding: the shell around generated tests must be a valid,
runnable project (dependency manifest, runner config, README) per platform."""

import json

from framework.codegen.ir import Platform, TestModel
from framework.codegen.scaffold import available_scaffolds, scaffold_files


def _model(platform, pkg="com.example.app", activity=".Main"):
    return TestModel(name="Flow", app_package=pkg, platform=platform, app_activity=activity, cases=[])


def test_js_android_scaffold_is_runnable():
    files = scaffold_files(_model(Platform.ANDROID), "js_webdriverio")
    pkg = json.loads(files["package.json"])
    assert pkg["scripts"]["test"] == "wdio run wdio.conf.js"
    assert "appium-uiautomator2-driver" in pkg["devDependencies"]
    assert "@wdio/appium-service" in pkg["devDependencies"]
    conf = files["wdio.conf.js"]
    assert "'appium:appPackage': 'com.example.app'" in conf
    assert "UiAutomator2" in conf
    assert "appium install" in files["README.md"] or "appium driver install uiautomator2" in files["README.md"]


def test_js_ios_scaffold_uses_bundle_and_xcuitest():
    files = scaffold_files(_model(Platform.IOS, pkg="com.example.ios", activity=None), "js_webdriverio")
    pkg = json.loads(files["package.json"])
    assert "appium-xcuitest-driver" in pkg["devDependencies"]
    conf = files["wdio.conf.js"]
    assert "'appium:bundleId': 'com.example.ios'" in conf
    assert "XCUITest" in conf
    assert "appPackage" not in conf


def test_python_scaffold_has_requirements_and_ini():
    files = scaffold_files(_model(Platform.ANDROID), "python_pytest")
    assert "Appium-Python-Client" in files["requirements.txt"]
    assert "[pytest]" in files["pytest.ini"]
    assert "testpaths = python_pytest\n" in files["pytest.ini"]  # points at its own dir
    assert "pytest-bdd" not in files["requirements.txt"]  # imperative target needs no bdd dep
    assert "pip install -r requirements.txt" in files["README.md"]


def test_python_bdd_scaffold_targets_bdd_dir_and_pulls_pytest_bdd():
    """Regression: the BDD scaffold used to write `testpaths = python_pytest` and
    omit pytest-bdd, so the generated project collected nothing and failed to
    import. It must point at its own dir and pull the dependency it imports."""
    files = scaffold_files(_model(Platform.ANDROID), "python_pytest_bdd")
    assert "testpaths = python_pytest_bdd\n" in files["pytest.ini"]
    assert "pytest-bdd" in files["requirements.txt"]


def test_js_cucumber_scaffold_uses_cucumber_framework_and_own_dir():
    """Regression: js_cucumber reused the mocha config pointing at
    `js_webdriverio/`, so feature files never ran. It must use the cucumber
    framework, load its step files, and glob its own directory."""
    files = scaffold_files(_model(Platform.ANDROID), "js_cucumber")
    conf = files["wdio.conf.js"]
    assert "framework: 'cucumber'" in conf
    assert "./js_cucumber/**/*.feature" in conf
    assert "./js_cucumber/**/*.steps.js" in conf
    pkg = json.loads(files["package.json"])
    assert "@wdio/cucumber-framework" in pkg["devDependencies"]
    assert "@wdio/mocha-framework" not in pkg["devDependencies"]


def test_js_webdriverio_scaffold_stays_mocha_in_own_dir():
    files = scaffold_files(_model(Platform.ANDROID), "js_webdriverio")
    conf = files["wdio.conf.js"]
    assert "framework: 'mocha'" in conf
    assert "./js_webdriverio/**/*.js" in conf
    assert "@wdio/mocha-framework" in json.loads(files["package.json"])["devDependencies"]


def test_unknown_target_has_no_scaffold():
    assert scaffold_files(_model(Platform.ANDROID), "kotlin_espresso") == {}
    assert "js_webdriverio" in available_scaffolds() and "python_pytest" in available_scaffolds()
