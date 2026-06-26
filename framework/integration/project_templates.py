"""
Test project templates and initialization

Creates new test automation projects with best practices structure.
"""

import textwrap


def get_pytest_ini_template() -> str:
    """pytest.ini template"""
    return textwrap.dedent("""
    [pytest]
    # pytest configuration
    testpaths = tests
    python_files = test_*.py
    python_classes = Test*
    python_functions = test_*

    # Markers
    markers =
        smoke: Smoke tests (critical path)
        regression: Full regression suite
        api: API-level tests
        ui: UI-level tests
        slow: Slow running tests
        skip_ci: Skip in CI environment

    # Output
    addopts =
        -v
        --strict-markers
        --tb=short
        --maxfail=5

    # Warnings
    filterwarnings =
        ignore::DeprecationWarning
    """).strip()


def get_conftest_template() -> str:
    """conftest.py template with common fixtures"""
    return textwrap.dedent("""
    '''
    Shared pytest fixtures for mobile test automation

    This file contains fixtures that are automatically discovered by pytest.
    '''

    import pytest
    from appium import webdriver
    from pathlib import Path


    @pytest.fixture(scope="session")
    def config():
        '''Load test configuration'''
        # TODO: Load from config file or environment
        return {
            'appium_server': 'http://localhost:4723',
            'platform': 'Android',  # or 'iOS'
            'app_path': Path(__file__).parent / 'apps' / 'app-debug.apk',
        }


    @pytest.fixture(scope="function")
    def driver(config):
        '''
        Appium driver fixture

        Creates a new driver instance for each test.
        Automatically quits after test completion.
        '''
        capabilities = {
            'platformName': config['platform'],
            'automationName': 'UiAutomator2' if config['platform'] == 'Android' else 'XCUITest',
            'app': str(config['app_path']),
            'newCommandTimeout': 300,
            'noReset': False,
        }

        driver = webdriver.Remote(
            config['appium_server'],
            capabilities
        )

        yield driver

        driver.quit()


    @pytest.fixture
    def api_client():
        '''API client fixture for API-level testing'''
        # TODO: Implement API client
        from utilities.api_client import APIClient
        client = APIClient(base_url='https://api.example.com')
        return client


    @pytest.fixture
    def test_user():
        '''Test user fixture with cleanup'''
        # TODO: Create test user via API
        user = {
            'username': 'test_user',
            'password': 'test_password',
            'email': 'test@example.com'
        }

        yield user

        # Cleanup after test
        # TODO: Delete test user via API
    """).strip()


def get_base_page_template() -> str:
    """Base Page Object template"""
    return textwrap.dedent("""
    '''
    Base Page Object class

    All Page Objects should inherit from this class.
    Provides common utilities for element interaction, waits, etc.
    '''

    from appium.webdriver.common.appiumby import AppiumBy
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from typing import Tuple, Optional


    class BasePage:
        '''Base class for all Page Objects'''

        def __init__(self, driver):
            self.driver = driver
            self.wait = WebDriverWait(driver, 10)

        def find_element(self, locator: Tuple[str, str], timeout: int = 10):
            '''
            Find element with explicit wait

            Args:
                locator: Tuple of (By, value)
                timeout: Maximum wait time in seconds

            Returns:
                WebElement
            '''
            wait = WebDriverWait(self.driver, timeout)
            return wait.until(EC.presence_of_element_located(locator))

        def find_elements(self, locator: Tuple[str, str], timeout: int = 10):
            '''Find multiple elements'''
            wait = WebDriverWait(self.driver, timeout)
            return wait.until(EC.presence_of_all_elements_located(locator))

        def click(self, locator: Tuple[str, str], timeout: int = 10):
            '''Click element with wait'''
            element = self.find_element(locator, timeout)
            element.click()

        def send_keys(self, locator: Tuple[str, str], text: str, timeout: int = 10):
            '''Send keys to element with wait'''
            element = self.find_element(locator, timeout)
            element.clear()
            element.send_keys(text)

        def get_text(self, locator: Tuple[str, str], timeout: int = 10) -> str:
            '''Get element text'''
            element = self.find_element(locator, timeout)
            return element.text

        def is_element_present(self, locator: Tuple[str, str], timeout: int = 5) -> bool:
            '''Check if element is present'''
            try:
                self.find_element(locator, timeout)
                return True
            except (TimeoutException, NoSuchElementException):
                return False

        def wait_for_element_visible(self, locator: Tuple[str, str], timeout: int = 10):
            '''Wait for element to be visible'''
            wait = WebDriverWait(self.driver, timeout)
            return wait.until(EC.visibility_of_element_located(locator))

        def wait_for_element_clickable(self, locator: Tuple[str, str], timeout: int = 10):
            '''Wait for element to be clickable'''
            wait = WebDriverWait(self.driver, timeout)
            return wait.until(EC.element_to_be_clickable(locator))

        def scroll_to_element(self, locator: Tuple[str, str]):
            '''Scroll to element (platform-specific implementation needed)'''
            # TODO: Implement platform-specific scrolling
            pass
    """).strip()


def get_example_page_template() -> str:
    """Example Page Object template"""
    return textwrap.dedent("""
    '''
    Login Page Object

    Example Page Object demonstrating best practices.
    '''

    from appium.webdriver.common.appiumby import AppiumBy
    from page_objects.base_page import BasePage


    class LoginPage(BasePage):
        '''Login screen Page Object'''

        # Locators
        username_field = (AppiumBy.ID, 'com.example:id/username')
        password_field = (AppiumBy.ID, 'com.example:id/password')
        login_button = (AppiumBy.ID, 'com.example:id/login_button')
        error_message = (AppiumBy.ID, 'com.example:id/error_message')

        # Actions
        def enter_username(self, username: str):
            '''Enter username'''
            self.send_keys(self.username_field, username)

        def enter_password(self, password: str):
            '''Enter password'''
            self.send_keys(self.password_field, password)

        def click_login(self):
            '''Click login button'''
            self.click(self.login_button)

        def login(self, username: str, password: str):
            '''
            Complete login flow

            Args:
                username: Username
                password: Password
            '''
            self.enter_username(username)
            self.enter_password(password)
            self.click_login()

        # Verifications
        def is_login_successful(self) -> bool:
            '''Check if login was successful (no error message)'''
            return not self.is_element_present(self.error_message, timeout=3)

        def get_error_message(self) -> str:
            '''Get error message text'''
            return self.get_text(self.error_message)
    """).strip()


def get_example_test_template() -> str:
    """Example test file template"""
    return textwrap.dedent("""
    '''
    Login functionality tests

    Example test file demonstrating best practices.
    '''

    import pytest
    from page_objects.login_page import LoginPage


    @pytest.mark.smoke
    class TestLogin:
        '''Login test suite'''

        def test_successful_login(self, driver, test_user):
            '''Test successful login with valid credentials'''
            # Given: User is on login screen
            login_page = LoginPage(driver)

            # When: User enters valid credentials and clicks login
            login_page.login(
                username=test_user['username'],
                password=test_user['password']
            )

            # Then: Login is successful
            assert login_page.is_login_successful()

        @pytest.mark.negative
        def test_login_with_invalid_password(self, driver, test_user):
            '''Test login failure with invalid password'''
            # Given: User is on login screen
            login_page = LoginPage(driver)

            # When: User enters invalid password
            login_page.login(
                username=test_user['username'],
                password='wrong_password'
            )

            # Then: Error message is displayed
            assert not login_page.is_login_successful()
            error = login_page.get_error_message()
            assert 'invalid' in error.lower() or 'incorrect' in error.lower()
    """).strip()


def get_api_client_template() -> str:
    """API client utility template"""
    return textwrap.dedent("""
    '''
    API Client utility

    For API-level testing and test data setup.
    '''

    import requests
    from typing import Optional


    class APIClient:
        '''Base API client for backend communication'''

        def __init__(self, base_url: str):
            self.base_url = base_url
            self.session = requests.Session()
            self.auth_token: Optional[str] = None

        def login(self, username: str, password: str) -> Dict:
            '''Authenticate and store token'''
            response = self.session.post(
                f'{self.base_url}/auth/login',
                json={'username': username, 'password': password}
            )
            response.raise_for_status()

            data = response.json()
            self.auth_token = data.get('token')
            self.session.headers.update({'Authorization': f'Bearer {self.auth_token}'})

            return data

        def create_user(self, user_data: Dict) -> Dict:
            '''Create test user'''
            response = self.session.post(
                f'{self.base_url}/users',
                json=user_data
            )
            response.raise_for_status()
            return response.json()

        def delete_user(self, user_id: str):
            '''Delete test user'''
            response = self.session.delete(f'{self.base_url}/users/{user_id}')
            response.raise_for_status()
    """).strip()


def get_readme_template(project_name: str) -> str:
    """README.md template"""
    return textwrap.dedent("""
    # {project_name} - Mobile Test Automation

    Automated test suite for {project_name} mobile application.

    ## Project Structure

    ```
    {project_name}/
    ├── page_objects/          # Page Object Model classes
    │   ├── __init__.py
    │   ├── base_page.py      # Base class for all pages
    │   └── login_page.py     # Example page object
    ├── tests/                 # Test cases
    │   ├── __init__.py
    │   ├── conftest.py       # Shared fixtures
    │   └── test_login.py     # Example tests
    ├── utilities/             # Helper utilities
    │   ├── __init__.py
    │   └── api_client.py     # API client for test data
    ├── data/                  # Test data files
    ├── reports/               # Test execution reports
    ├── pytest.ini             # pytest configuration
    ├── requirements.txt       # Python dependencies
    └── README.md              # This file
    ```

    ## Setup

    1. **Install Python 3.13+**

    2. **Create virtual environment:**
       ```bash
       python -m venv .venv
       source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
       ```

    3. **Install dependencies:**
       ```bash
       pip install -r requirements.txt
       ```

    4. **Configure test environment:**
       - Update `tests/conftest.py` with your app path and Appium server
       - Place your app (APK/IPA) in `data/apps/`

    5. **Start Appium server:**
       ```bash
       appium
       ```

    ## Running Tests

    **Run all tests:**
    ```bash
    pytest
    ```

    **Run smoke tests only:**
    ```bash
    pytest -m smoke
    ```

    **Run specific test file:**
    ```bash
    pytest tests/test_login.py
    ```

    **Run with HTML report:**
    ```bash
    pytest --html=reports/report.html
    ```

    **Run in parallel:**
    ```bash
    pytest -n auto  # Uses all CPU cores
    ```

    ## Test Markers

    - `@pytest.mark.smoke` - Critical path tests
    - `@pytest.mark.regression` - Full regression suite
    - `@pytest.mark.api` - API-level tests
    - `@pytest.mark.ui` - UI-level tests
    - `@pytest.mark.negative` - Negative test cases

    ## Page Object Pattern

    This project follows the Page Object Model (POM) design pattern:

    - Each screen/page has a corresponding Page Object class
    - Locators are defined as class attributes
    - Actions are methods that interact with the page
    - Verifications return boolean or data

    Example:
    ```python
    from page_objects.login_page import LoginPage

    def test_login(driver):
        login_page = LoginPage(driver)
        login_page.login('user', 'password')
        assert login_page.is_login_successful()
    ```

    ## Integration with Observe Framework

    This project was generated by Mobile Observe & Test Framework.

    To regenerate or update tests based on new observations:
    ```bash
    observe generate tests --match-style
    ```

    ## CI/CD Integration

    See `.github/workflows/` (or `.gitlab-ci.yml`) for CI/CD configuration.

    ## Contributing

    1. Add new Page Objects in `page_objects/`
    2. Add new tests in `tests/`
    3. Follow existing naming conventions
    4. Run tests before committing
    5. Update documentation as needed
    """).strip()


def get_gitignore_template() -> str:
    """.gitignore template"""
    return textwrap.dedent("""
    # Python
    __pycache__/
    *.py[cod]
    *$py.class
    *.so
    .Python
    .venv/
    venv/
    ENV/
    env/

    # pytest
    .pytest_cache/
    .coverage
    htmlcov/
    *.log

    # IDE
    .vscode/
    .idea/
    *.swp
    *.swo
    *~

    # Reports
    reports/*.html
    reports/*.xml
    reports/*.json
    screenshots/

    # Appium
    appium.log

    # OS
    .DS_Store
    Thumbs.db

    # Apps (keep directory but ignore files)
    data/apps/*.apk
    data/apps/*.ipa
    !data/apps/.gitkeep
    """).strip()


PROJECT_TEMPLATES = {
    'pytest.ini': get_pytest_ini_template,
    'tests/conftest.py': get_conftest_template,
    'page_objects/__init__.py': lambda: '',
    'page_objects/base_page.py': get_base_page_template,
    'page_objects/login_page.py': get_example_page_template,
    'tests/__init__.py': lambda: '',
    'tests/test_login.py': get_example_test_template,
    'utilities/__init__.py': lambda: '',
    'utilities/api_client.py': get_api_client_template,
    'data/apps/.gitkeep': lambda: '',
    'reports/.gitkeep': lambda: '',
    '.gitignore': get_gitignore_template,
}
