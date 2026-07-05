"""Emitters must produce a platform-correct Appium session for BOTH Android and
iOS across every non-Kotlin target. iOS drives XCUITest (bundleId), Android
drives UiAutomator2 (appPackage) — mixing them yields an un-runnable test."""

import pytest

from framework.crawler.app_crawler import CrawlResult, parse_screen
from framework.crawler.to_codegen import build_test_model
from framework.codegen import get_emitter

IOS_XML = (
    '<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="Shop" '
    'x="0" y="0" width="390" height="844">'
    '<XCUIElementTypeButton type="XCUIElementTypeButton" name="login_btn" label="Log In" '
    'enabled="true" x="20" y="250" width="350" height="50"/></XCUIElementTypeApplication>'
)
ANDROID_XML = (
    '<hierarchy><node class="android.widget.Button" resource-id="com.x:id/login" '
    'text="Log In" content-desc="" clickable="true" bounds="[0,0][100,50]" package="com.x"/></hierarchy>'
)

TARGETS = ["python_pytest", "python_pytest_bdd", "java_testng", "java_cucumber", "js_webdriverio"]


def _model(xml, pkg):
    s = parse_screen(xml)
    return build_test_model(CrawlResult(screens={s.fingerprint: s}), app_package=pkg, app_activity=".Main")


@pytest.mark.parametrize("target", TARGETS)
def test_ios_session_is_xcuitest(target):
    code = "\n".join(get_emitter(target).emit(_model(IOS_XML, "com.shop.app")).values())
    assert "XCUITest" in code or "bundleId" in code or "bundle_id" in code
    # must NOT wire the Android automation engine / package caps into an iOS test
    assert "UiAutomator2Options" not in code
    assert "setAppPackage" not in code and "options.app_package" not in code


@pytest.mark.parametrize("target", TARGETS)
def test_android_session_is_uiautomator2(target):
    code = "\n".join(get_emitter(target).emit(_model(ANDROID_XML, "com.x")).values())
    assert "XCUITestOptions" not in code and "IOSDriver" not in code
    if target.startswith("java") or target.startswith("python"):
        assert "UiAutomator2" in code
