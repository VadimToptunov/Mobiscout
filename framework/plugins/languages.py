"""
Language Plugins for Test Generation

Provides plugins for generating tests in different programming languages:
- Python (pytest)
- Java (JUnit, TestNG)
- Kotlin (JUnit5)
- Swift (XCTest)
- TypeScript (Jest)
- etc.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TestCase:
    """Represents a generated test case."""
    name: str
    description: str = ""
    steps: List[str] = field(default_factory=list)
    assertions: List[str] = field(default_factory=list)
    setup: List[str] = field(default_factory=list)
    teardown: List[str] = field(default_factory=list)


class LanguagePlugin(ABC):
    """
    Abstract base class for language-specific test generators.

    Each plugin implements test generation for a specific programming language
    and test framework.
    """

    name: str = "base"
    file_extension: str = ".txt"
    test_framework: str = "generic"

    @abstractmethod
    def generate_test_file(
            self,
            test_cases: List[TestCase],
            output_path: Path,
            class_name: str = "GeneratedTest"
    ) -> str:
        """
        Generate a test file from test cases.

        Args:
            test_cases: List of test cases to generate
            output_path: Output file path
            class_name: Name of the test class

        Returns:
            Generated test code as string
        """
        pass

    @abstractmethod
    def generate_page_object(
            self,
            screen_name: str,
            elements: List[Dict[str, Any]],
            output_path: Path
    ) -> str:
        """
        Generate a page object class.

        Args:
            screen_name: Name of the screen/page
            elements: List of UI elements with selectors
            output_path: Output file path

        Returns:
            Generated page object code as string
        """
        pass

    def get_imports(self) -> List[str]:
        """Get required imports for the language/framework."""
        return []

    def format_selector(self, selector_type: str, selector_value: str) -> str:
        """Format a selector for the language."""
        return f'"{selector_value}"'


class PythonPlugin(LanguagePlugin):
    """Python test generator using pytest."""

    name = "python"
    file_extension = ".py"
    test_framework = "pytest"

    def generate_test_file(
            self,
            test_cases: List[TestCase],
            output_path: Path,
            class_name: str = "GeneratedTest"
    ) -> str:
        lines = [
            '"""Auto-generated tests."""',
            'import pytest',
            'from appium import webdriver',
            '',
            '',
            f'class Test{class_name}:',
            '    """Generated test class."""',
            '',
        ]

        for tc in test_cases:
            lines.append(f'    def test_{tc.name}(self, driver):')
            lines.append(f'        """{tc.description}"""')
            for step in tc.steps:
                lines.append(f'        {step}')
            for assertion in tc.assertions:
                lines.append(f'        {assertion}')
            lines.append('')

        code = '\n'.join(lines)
        output_path.write_text(code, encoding='utf-8')
        return code

    def generate_page_object(
            self,
            screen_name: str,
            elements: List[Dict[str, Any]],
            output_path: Path
    ) -> str:
        lines = [
            '"""Auto-generated page object."""',
            'from appium.webdriver.common.appiumby import AppiumBy',
            '',
            '',
            f'class {screen_name}Page:',
            f'    """Page object for {screen_name}."""',
            '',
            '    def __init__(self, driver):',
            '        self.driver = driver',
            '',
        ]

        for elem in elements:
            name = elem.get('name', 'element')
            selector = elem.get('selector', '')
            selector_type = elem.get('type', 'id')

            lines.append(f'    @property')
            lines.append(f'    def {name}(self):')
            lines.append(f'        return self.driver.find_element(AppiumBy.{selector_type.upper()}, "{selector}")')
            lines.append('')

        code = '\n'.join(lines)
        output_path.write_text(code, encoding='utf-8')
        return code

    def get_imports(self) -> List[str]:
        return [
            'import pytest',
            'from appium import webdriver',
            'from appium.webdriver.common.appiumby import AppiumBy',
        ]


class JavaPlugin(LanguagePlugin):
    """Java test generator using JUnit."""

    name = "java"
    file_extension = ".java"
    test_framework = "junit"

    def generate_test_file(
            self,
            test_cases: List[TestCase],
            output_path: Path,
            class_name: str = "GeneratedTest"
    ) -> str:
        lines = [
            'import org.junit.jupiter.api.*;',
            'import io.appium.java_client.AppiumDriver;',
            'import static org.junit.jupiter.api.Assertions.*;',
            '',
            f'public class {class_name}Test {{',
            '',
            '    private AppiumDriver driver;',
            '',
        ]

        for tc in test_cases:
            lines.append('    @Test')
            lines.append(f'    public void test{tc.name.title()}() {{')
            lines.append(f'        // {tc.description}')
            for step in tc.steps:
                lines.append(f'        {step}')
            for assertion in tc.assertions:
                lines.append(f'        {assertion}')
            lines.append('    }')
            lines.append('')

        lines.append('}')

        code = '\n'.join(lines)
        output_path.write_text(code, encoding='utf-8')
        return code

    def generate_page_object(
            self,
            screen_name: str,
            elements: List[Dict[str, Any]],
            output_path: Path
    ) -> str:
        lines = [
            'import io.appium.java_client.AppiumDriver;',
            'import io.appium.java_client.pagefactory.*;',
            'import org.openqa.selenium.WebElement;',
            '',
            f'public class {screen_name}Page {{',
            '',
            '    private AppiumDriver driver;',
            '',
        ]

        for elem in elements:
            name = elem.get('name', 'element')
            selector = elem.get('selector', '')
            selector_type = elem.get('type', 'id')

            lines.append(f'    @AndroidFindBy({selector_type} = "{selector}")')
            lines.append(f'    private WebElement {name};')
            lines.append('')

        lines.append(f'    public {screen_name}Page(AppiumDriver driver) {{')
        lines.append('        this.driver = driver;')
        lines.append('        PageFactory.initElements(new AppiumFieldDecorator(driver), this);')
        lines.append('    }')
        lines.append('}')

        code = '\n'.join(lines)
        output_path.write_text(code, encoding='utf-8')
        return code

    def get_imports(self) -> List[str]:
        return [
            'import org.junit.jupiter.api.*;',
            'import io.appium.java_client.AppiumDriver;',
            'import io.appium.java_client.pagefactory.*;',
        ]


class KotlinPlugin(LanguagePlugin):
    """Kotlin test generator using JUnit5."""

    name = "kotlin"
    file_extension = ".kt"
    test_framework = "junit5"

    def generate_test_file(
            self,
            test_cases: List[TestCase],
            output_path: Path,
            class_name: str = "GeneratedTest"
    ) -> str:
        lines = [
            'import org.junit.jupiter.api.*',
            'import io.appium.java_client.AppiumDriver',
            '',
            f'class {class_name}Test {{',
            '',
            '    private lateinit var driver: AppiumDriver',
            '',
        ]

        for tc in test_cases:
            lines.append('    @Test')
            lines.append(f'    fun `test {tc.name}`() {{')
            lines.append(f'        // {tc.description}')
            for step in tc.steps:
                lines.append(f'        {step}')
            for assertion in tc.assertions:
                lines.append(f'        {assertion}')
            lines.append('    }')
            lines.append('')

        lines.append('}')

        code = '\n'.join(lines)
        output_path.write_text(code, encoding='utf-8')
        return code

    def generate_page_object(
            self,
            screen_name: str,
            elements: List[Dict[str, Any]],
            output_path: Path
    ) -> str:
        lines = [
            'import io.appium.java_client.AppiumDriver',
            'import io.appium.java_client.pagefactory.*',
            'import org.openqa.selenium.WebElement',
            '',
            f'class {screen_name}Page(private val driver: AppiumDriver) {{',
            '',
            '    init {{',
            '        PageFactory.initElements(AppiumFieldDecorator(driver), this)',
            '    }}',
            '',
        ]

        for elem in elements:
            name = elem.get('name', 'element')
            selector = elem.get('selector', '')
            selector_type = elem.get('type', 'id')

            lines.append(f'    @AndroidFindBy({selector_type} = "{selector}")')
            lines.append(f'    lateinit var {name}: WebElement')
            lines.append('')

        lines.append('}')

        code = '\n'.join(lines)
        output_path.write_text(code, encoding='utf-8')
        return code

    def get_imports(self) -> List[str]:
        return [
            'import org.junit.jupiter.api.*',
            'import io.appium.java_client.AppiumDriver',
        ]


# Plugin registry
PLUGINS: Dict[str, LanguagePlugin] = {
    'python': PythonPlugin(),
    'java': JavaPlugin(),
    'kotlin': KotlinPlugin(),
}


def get_plugin(language: str) -> Optional[LanguagePlugin]:
    """
    Get plugin for a specific language.

    Args:
        language: Language name (python, java, kotlin, etc.)

    Returns:
        LanguagePlugin instance or None if not found
    """
    return PLUGINS.get(language.lower())


def list_languages() -> List[str]:
    """
    List all available language plugins.

    Returns:
        List of supported language names
    """
    return list(PLUGINS.keys())
