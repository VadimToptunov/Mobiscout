"""Cross-platform locator rendering: a visible-text locator must be Android's
uiautomator ``text()`` on Android but an XPath-by-``@label`` on iOS (XCUITest
has no text selector). Regression guard for the cross-platform claim."""

from framework.codegen.ir import Platform, SelectorStrategy
from framework.crawler.app_crawler import CrawlElement, CrawlResult, parse_screen
from framework.crawler.to_codegen import build_test_model, selector_for
from framework.codegen import get_emitter

IOS_XML = """<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="ShopApp" x="0" y="0" width="390" height="844">
  <XCUIElementTypeButton type="XCUIElementTypeButton" name="login_btn" label="Log In" enabled="true" x="20" y="250" width="350" height="50"/>
  <XCUIElementTypeButton type="XCUIElementTypeButton" name="" label="Forgot password?" enabled="true" x="120" y="320" width="150" height="30"/>
</XCUIElementTypeApplication>"""


def _text_element():
    return CrawlElement(
        resource_id="", text="Log In", content_desc="", class_name="Button", clickable=True, bounds=(0, 0, 100, 40)
    )


def test_text_selector_is_uiautomator_on_android():
    sel = selector_for(_text_element(), platform="android")
    assert sel.strategy is SelectorStrategy.TEXT
    assert sel.value == "Log In"


def test_text_selector_is_xpath_by_label_on_ios():
    sel = selector_for(_text_element(), platform="ios")
    assert sel.strategy is SelectorStrategy.XPATH
    assert sel.value == '//*[@label="Log In" or @name="Log In"]'


def test_ios_crawl_builds_ios_model_without_uiautomator():
    screen = parse_screen(IOS_XML)
    assert screen.platform == "ios"
    model = build_test_model(CrawlResult(screens={screen.fingerprint: screen}), app_package="com.shop.app")
    assert model.platform is Platform.IOS
    code = list(get_emitter("python_pytest").emit(model).values())[0]
    # An iOS suite must never emit an Android-only uiautomator selector.
    assert "UiSelector" not in code
    assert "login_btn" in code  # accessibility id preserved
    assert "@label=" in code and "Forgot password?" in code  # label-only element -> xpath
