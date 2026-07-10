"""Navigation tests — drive the Page Objects (POM style)."""

from pages.screen2_page import Screen2Page
from pages.welcome_back_page import WelcomeBackPage

def test_navigate_1(driver):
    """WelcomeBack -> Screen2 via sign_in."""
    WelcomeBackPage(driver).sign_in().click()
    assert Screen2Page(driver).search_products().is_displayed()
