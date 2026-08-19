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
    assert scaffold_files(_model(Platform.ANDROID), "ruby_rspec") == {}
    assert "js_webdriverio" in available_scaffolds() and "python_pytest" in available_scaffolds()


def test_every_plugin_target_is_scaffoldable():
    """Regression: the "Create a runnable project" checkbox was a silent no-op for
    Java and Kotlin (only Python/JS had scaffolders). All four languages the plugin
    offers must now produce a project shell."""
    for target in (
        "python_pytest",
        "python_pytest_bdd",
        "java_testng",
        "java_cucumber",
        "kotlin_appium",
        "kotlin_espresso",
        "js_webdriverio",
        "js_cucumber",
    ):
        assert scaffold_files(_model(Platform.ANDROID), target), f"{target} has no scaffold"


def test_java_testng_scaffold_runs_via_testng_xml():
    files = scaffold_files(_model(Platform.IOS, pkg="com.example.ios", activity=None), "java_testng")
    pom = files["pom.xml"]
    assert "<artifactId>java-client</artifactId>" in pom  # Appium
    assert "<artifactId>testng</artifactId>" in pom
    assert "<testSourceDirectory>${project.basedir}/java_testng</testSourceDirectory>" in pom
    assert "<suiteXmlFile>testng.xml</suiteXmlFile>" in pom
    # The flat file declares `package generated`, so the suite must name the class
    # by FQN (path→FQN inference would look for a default-package class and miss it).
    assert '<class name="generated.Flow"/>' in files["testng.xml"]
    assert "mvn test" in files["README.md"]


def test_java_cucumber_scaffold_has_runner_and_cucumber_deps():
    files = scaffold_files(_model(Platform.ANDROID), "java_cucumber")
    assert "<artifactId>cucumber-testng</artifactId>" in files["pom.xml"]
    runner = files["java_cucumber/RunCucumberTest.java"]
    assert 'features = "java_cucumber", glue = "generated"' in runner
    assert "AbstractTestNGCucumberTests" in runner
    assert '<class name="generated.RunCucumberTest"/>' in files["testng.xml"]


def test_kotlin_appium_scaffold_is_gradle_jvm_junit5():
    files = scaffold_files(_model(Platform.IOS, activity=None), "kotlin_appium")
    build = files["build.gradle.kts"]
    assert 'kotlin("jvm")' in build
    assert '"io.appium:java-client' in build
    assert 'kotlin.srcDir("kotlin_appium")' in build
    assert "useJUnitPlatform()" in build
    assert files["settings.gradle.kts"].strip() == 'rootProject.name = "mobile-tests"'


def test_kotlin_espresso_scaffold_is_androidtest_snippet_not_standalone():
    """Espresso runs inside the app's own module, so the scaffold is an androidTest
    dependency snippet + instructions — not a standalone runnable project."""
    files = scaffold_files(_model(Platform.ANDROID), "kotlin_espresso")
    assert "pom.xml" not in files and "build.gradle.kts" not in files
    snippet = files["espresso.gradle.kts"]
    assert "androidTestImplementation" in snippet and "espresso-core" in snippet
    assert "connectedAndroidTest" in files["README.md"]
