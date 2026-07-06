"""Shared pytest fixtures — one Appium session per test."""

import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options


@pytest.fixture()
def driver():
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.app_package = 'com.example.shop'
    options.app_activity = '.MainActivity'
    drv = webdriver.Remote("http://localhost:4723", options=options)
    yield drv
    drv.quit()
