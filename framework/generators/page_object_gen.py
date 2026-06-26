"""
Page Object Generator

Generates Page Object classes from App Model screens.
"""

from pathlib import Path
from typing import List

from jinja2 import Template

from framework.model.app_model import Screen

PAGE_OBJECT_TEMPLATE = """
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from typing import Optional, List, Tuple
import os


class {{ class_name }}:
    \"\"\"
    Page Object for {{ screen.name }} screen

    Generated from App Model
    Supports fallback selector strategies for robust element identification
    \"\"\"

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 10)
        self.short_wait = WebDriverWait(driver, 2)  # For fallback attempts
        self._page_object_file = __file__  # Store file path for healing reports

    # Selectors with fallback strategies
{% for element in screen.elements %}
    {{ element.id | upper }}_SELECTOR = {
        "android": {{ element.selector.android | tojson }},
        "ios": {{ element.selector.ios | tojson }},
        "android_fallback": {{ element.selector.android_fallback | tojson }},
        "ios_fallback": {{ element.selector.ios_fallback | tojson }},
        "stability": "{{ element.selector.stability }}"
    }
{% endfor %}

    def _parse_selector(self, selector: str) -> Tuple[str, str]:
        \"\"\"
        Parse selector string into (strategy, value) tuple

        Formats:
        - id:resource_id -> (AppiumBy.ID, resource_id)
        - xpath://path -> (AppiumBy.XPATH, //path)
        - accessibility:id -> (AppiumBy.ACCESSIBILITY_ID, id)
        - text:Button -> (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Button")')
        - class:android.widget.Button -> (AppiumBy.CLASS_NAME, android.widget.Button)
        \"\"\"
        if ':' in selector:
            strategy, value = selector.split(':', 1)

            if strategy == 'id':
                return (AppiumBy.ID, value)
            elif strategy == 'xpath':
                return (AppiumBy.XPATH, value)
            elif strategy == 'accessibility':
                return (AppiumBy.ACCESSIBILITY_ID, value)
            elif strategy == 'text':
                platform = self.driver.capabilities.get('platformName', '').lower()
                if platform == 'android':
                    return (AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{value}")')
                else:
                    return (AppiumBy.IOS_PREDICATE, f'label == "{value}"')
            elif strategy == 'class':
                return (AppiumBy.CLASS_NAME, value)
            elif strategy == 'name':
                return (AppiumBy.NAME, value)

        # Default: treat as XPath if starts with //, otherwise ID
        if selector.startswith('//'):
            return (AppiumBy.XPATH, selector)
        elif selector.startswith('~'):
            return (AppiumBy.ACCESSIBILITY_ID, selector[1:])
        else:
            return (AppiumBy.ID, selector)

    def _report_fallback_usage(
        self,
        element_name: str,
        primary_selector: str,
        successful_fallback: str,
        fallback_index: int
    ):
        \"\"\"
        Report fallback usage to SelectorHealer for auto-updating Page Objects.

        This method is called when a fallback selector succeeds after primary fails.
        \"\"\"
        try:
            from framework.ml.selector_healer import SelectorHealer

            platform = self.driver.capabilities.get('platformName', '').lower()

            # Get or create singleton healer instance
            if not hasattr(self, '_selector_healer'):
                self._selector_healer = SelectorHealer()

            self._selector_healer.report_fallback_usage(
                element_name=element_name,
                page_object_file=self._page_object_file,
                primary_selector=primary_selector,
                successful_fallback=successful_fallback,
                fallback_index=fallback_index,
                platform=platform
            )
        except (AttributeError, TypeError, ValueError, OSError) as e:
            # Don't fail test if reporting fails
            print(f"[SelectorHealer] Failed to report fallback: {e}")

    def _find_element_with_fallback(self, selector_dict: dict, element_name: str = "element"):
        \"\"\"
        Find element using primary selector with fallback strategies

        Tries selectors in order:
        1. Primary platform-specific selector
        2. Fallback selectors (in order of stability)
        3. Raises NoSuchElementException if all fail
        \"\"\"
        platform = self.driver.capabilities.get('platformName', '').lower()

        # Get primary and fallback selectors for platform
        if platform == 'android':
            primary = selector_dict.get('android')
            fallbacks = selector_dict.get('android_fallback', [])
        elif platform == 'ios':
            primary = selector_dict.get('ios')
            fallbacks = selector_dict.get('ios_fallback', [])
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        stability = selector_dict.get('stability', 'unknown')

        # Try primary selector first
        if primary:
            try:
                by, value = self._parse_selector(primary)
                element = self.short_wait.until(
                    EC.presence_of_element_located((by, value))
                )
                return element
            except (TimeoutException, NoSuchElementException) as e:
                print(f"[SelectorFallback] Primary selector failed for {element_name}: {primary}")
                print(f"[SelectorFallback] Trying {len(fallbacks)} fallback(s)...")

        # Try fallback selectors
        for idx, fallback_selector in enumerate(fallbacks, 1):
            try:
                by, value = self._parse_selector(fallback_selector)
                element = self.short_wait.until(
                    EC.presence_of_element_located((by, value))
                )
                print(f"[SelectorFallback] Success with fallback #{idx}: {fallback_selector}")

                # Report fallback usage to SelectorHealer
                self._report_fallback_usage(
                    element_name=element_name,
                    primary_selector=primary,
                    successful_fallback=fallback_selector,
                    fallback_index=idx - 1
                )

                return element
            except (TimeoutException, NoSuchElementException):
                print(f"[SelectorFallback] Fallback #{idx} failed: {fallback_selector}")
                continue

        # All strategies failed
        raise NoSuchElementException(
            f"Element '{element_name}' not found using primary or {len(fallbacks)} fallback selectors. "
            f"Stability: {stability}. Consider updating selectors."
        )

{% for element in screen.elements %}
    def get_{{ element.id }}(self):
        \"\"\"
        Get {{ element.id }} element

        Stability: {{ element.selector.stability }}
        Uses fallback strategies if primary selector fails
        \"\"\"
        return self._find_element_with_fallback(
            self.{{ element.id | upper }}_SELECTOR,
            element_name="{{ element.id }}"
        )

{% endfor %}

    # Actions
{% for action in screen.actions %}
    def {{ action.name }}(self{% for param in action.parameters %}, {{ param.name }}: {{ param.type }}{% endfor %}):
        \"\"\"{{ action.description or action.name }}\"\"\"
{% if action.target_element %}
        element = self.get_{{ action.target_element }}()
{% endif %}
{% if action.action_type == 'tap' %}
        element.click()
{% elif action.action_type == 'input' %}
        element.clear()
        element.send_keys({{ action.parameters[0].name if action.parameters else 'text' }})
{% elif action.action_type == 'swipe' %}
        # Swipe action
        self.driver.swipe(start_x=element.location['x'],
                         start_y=element.location['y'],
                         end_x=element.location['x'] + 200,
                         end_y=element.location['y'],
                         duration=500)
{% else %}
        # {{ action.action_type }} action
        element.click()
{% endif %}
{% if action.triggers_api %}
        # API call: {{ action.triggers_api }}
{% endif %}
{% if action.wait_for %}
        # Wait for: {{ action.wait_for }}
        import time
        time.sleep(1)
{% endif %}

{% endfor %}

    def is_displayed(self) -> bool:
        \"\"\"Check if screen is currently displayed\"\"\"
        try:
{% if screen.elements %}
            self.get_{{ screen.elements[0].id }}()
            return True
{% else %}
            return True
{% endif %}
        except Exception:
            return False

    def wait_until_displayed(self, timeout: int = 10):
        \"\"\"Wait until screen is displayed\"\"\"
        from selenium.common.exceptions import TimeoutException
        import time

        end_time = time.time() + timeout
        while time.time() < end_time:
            if self.is_displayed():
                return True
            time.sleep(0.5)

        raise TimeoutException(f"{{ screen.name }} screen not displayed after {timeout}s")
"""


def generate_page_object(screen: Screen, output_dir: Path) -> Path:
    """
    Generate Page Object class for screen

    Args:
        screen: Screen model
        output_dir: Output directory for generated file

    Returns:
        Path to generated file
    """
    # Create class name
    class_name = f"{screen.name.replace('Screen', '').replace(' ', '')}Page"

    # Render template
    template = Template(PAGE_OBJECT_TEMPLATE)
    content = template.render(
        screen=screen,
        class_name=class_name
    )

    # Write to file
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"{class_name.lower()}.py"
    file_path.write_text(content)

    return file_path


def generate_all_page_objects(screens: List[Screen], output_dir: Path) -> List[Path]:
    """
    Generate Page Objects for all screens

    Args:
        screens: List of screen models
        output_dir: Output directory

    Returns:
        List of generated file paths
    """
    generated_files = []

    for screen in screens:
        file_path = generate_page_object(screen, output_dir)
        generated_files.append(file_path)

    # Generate __init__.py
    init_content = "# Generated Page Objects\n\n"
    for screen in screens:
        class_name = f"{screen.name.replace('Screen', '').replace(' ', '')}Page"
        init_content += f"from .{class_name.lower()} import {class_name}\n"

    init_content += "\n__all__ = [\n"
    for screen in screens:
        class_name = f"{screen.name.replace('Screen', '').replace(' ', '')}Page"
        init_content += f"    '{class_name}',\n"
    init_content += "]\n"

    init_path = output_dir / "__init__.py"
    init_path.write_text(init_content)
    generated_files.append(init_path)

    return generated_files
