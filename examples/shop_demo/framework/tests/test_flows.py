"""Flow tests — form-filling, journeys and negative cases, through the Page Objects."""

from pages.running_shoes_page import RunningShoesPage
from pages.screen2_page import Screen2Page
from pages.welcome_back_page import WelcomeBackPage
from pages.your_cart_page import YourCartPage

def test_welcome_back_screen_shows_expected_controls(driver):
    """The welcome back screen shows its expected controls"""
    assert WelcomeBackPage(driver).welcome_back().is_displayed()
    assert WelcomeBackPage(driver).email().is_displayed()
    assert WelcomeBackPage(driver).email().is_enabled()
    assert WelcomeBackPage(driver).password().is_displayed()
    assert WelcomeBackPage(driver).password().is_enabled()
    assert WelcomeBackPage(driver).remember_me().is_displayed()
    assert WelcomeBackPage(driver).remember_me().is_enabled()
    assert WelcomeBackPage(driver).sign_in().is_displayed()
    assert WelcomeBackPage(driver).sign_in().is_enabled()
    assert WelcomeBackPage(driver).forgot_password().is_displayed()
    assert WelcomeBackPage(driver).forgot_password().is_enabled()

def test_search_products_screen_shows_expected_controls(driver):
    """The search products screen shows its expected controls"""
    WelcomeBackPage(driver).sign_in().click()
    assert Screen2Page(driver).search_products().is_displayed()
    assert Screen2Page(driver).search_products().is_enabled()
    assert Screen2Page(driver).running__shoes().is_displayed()
    assert Screen2Page(driver).running__shoes().is_enabled()
    assert Screen2Page(driver).backpack().is_displayed()
    assert Screen2Page(driver).backpack().is_enabled()
    assert Screen2Page(driver).cart().is_displayed()
    assert Screen2Page(driver).cart().is_enabled()

def test_running_shoes_screen_shows_expected_controls(driver):
    """The running shoes screen shows its expected controls"""
    WelcomeBackPage(driver).sign_in().click()
    Screen2Page(driver).running__shoes().click()
    assert RunningShoesPage(driver).running__shoes().is_displayed()
    assert RunningShoesPage(driver).add_to_cart().is_displayed()
    assert RunningShoesPage(driver).add_to_cart().is_enabled()

def test_your_cart_screen_shows_expected_controls(driver):
    """The your cart screen shows its expected controls"""
    WelcomeBackPage(driver).sign_in().click()
    Screen2Page(driver).cart().click()
    assert YourCartPage(driver).your_cart().is_displayed()
    assert YourCartPage(driver).place_order().is_displayed()
    assert YourCartPage(driver).place_order().is_enabled()

def test_tapping_sign_in_opens_search_products(driver):
    """Tapping Sign in opens the search products screen"""
    WelcomeBackPage(driver).sign_in().click()
    assert Screen2Page(driver).search_products().is_displayed()

def test_journey_from_sign_in_to_add_to_cart(driver):
    """Multi-step path (4 screens): screen 1 → screen 2 → screen 3 → screen 4"""
    WelcomeBackPage(driver).email().send_keys('test@example.com')
    WelcomeBackPage(driver).password().send_keys('Password123!')
    WelcomeBackPage(driver).remember_me().click()
    WelcomeBackPage(driver).sign_in().click()
    assert Screen2Page(driver).search_products().is_displayed()
    Screen2Page(driver).search_products().send_keys('test')
    Screen2Page(driver).running__shoes().click()
    assert RunningShoesPage(driver).running__shoes().is_displayed()
    RunningShoesPage(driver).add_to_cart().click()
    assert YourCartPage(driver).your_cart().is_displayed()

def test_journey_from_sign_in_to_cart(driver):
    """Multi-step path (3 screens): screen 1 → screen 2 → screen 4"""
    WelcomeBackPage(driver).email().send_keys('test@example.com')
    WelcomeBackPage(driver).password().send_keys('Password123!')
    WelcomeBackPage(driver).remember_me().click()
    WelcomeBackPage(driver).sign_in().click()
    assert Screen2Page(driver).search_products().is_displayed()
    Screen2Page(driver).search_products().send_keys('test')
    Screen2Page(driver).cart().click()
    assert YourCartPage(driver).your_cart().is_displayed()

def test_rejects_invalid_input_on_welcome_back(driver):
    """Submitting invalid data on the welcome back form is rejected"""
    WelcomeBackPage(driver).email().send_keys('not-an-email')
    WelcomeBackPage(driver).password().send_keys('1')
    WelcomeBackPage(driver).sign_in().click()
    assert WelcomeBackPage(driver).sign_in().is_displayed()
