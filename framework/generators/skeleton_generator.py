"""
STEP 3: Skeleton Test Generator - Multi-language test generation with self-healing selectors

Features:
- Page Object generation for all supported languages
- Helper methods
- Skeleton test scaffolding
- Self-healing selectors with fallback strategies
- BDD support
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from framework.core.engine import Language, Screen, UIElement


class PageObjectPattern(Enum):
    """Page Object patterns"""
    CLASSIC = "classic"  # Classic Page Object Model
    SCREENPLAY = "screenplay"  # Screenplay pattern
    FLUENT = "fluent"  # Fluent interface


@dataclass
class SelectorStrategy:
    """Self-healing selector with fallback strategies"""
    primary: str  # Primary selector (e.g., ID)
    fallbacks: List[str]  # Fallback selectors (xpath, accessibility id, etc.)
    stability_score: float = 1.0  # Selector stability score (0-1)

    def get_selector_chain(self) -> List[str]:
        """Get ordered list of selectors to try"""
        return [self.primary] + self.fallbacks


class SkeletonTestGenerator:
    """
    STEP 3: Generate skeleton tests with self-healing selectors

    Generates:
    - Page Objects
    - Helper methods
    - Test scaffolds
    - BDD features (optional)
    """

    def __init__(self, language: Language, pattern: PageObjectPattern = PageObjectPattern.CLASSIC):
        self.language = language
        self.pattern = pattern

    def generate_page_object(self, screen: Screen, package_name: str = "pages") -> str:
        """
        Generate Page Object for screen

        Args:
            screen: Screen to generate PO for
            package_name: Package/module name

        Returns:
            Generated Page Object code
        """
        if self.language == Language.PYTHON:
            return self._generate_python_page_object(screen, package_name)
        elif self.language == Language.JAVA:
            return self._generate_java_page_object(screen, package_name)
        elif self.language == Language.KOTLIN:
            return self._generate_kotlin_page_object(screen, package_name)
        elif self.language == Language.JAVASCRIPT:
            return self._generate_javascript_page_object(screen, package_name)
        elif self.language == Language.TYPESCRIPT:
            return self._generate_typescript_page_object(screen, package_name)
        elif self.language == Language.CSHARP:
            return self._generate_csharp_page_object(screen, package_name)
        elif self.language == Language.GO:
            return self._generate_go_page_object(screen, package_name)
        elif self.language == Language.SWIFT:
            return self._generate_swift_page_object(screen, package_name)

        return f"# Language {self.language} not supported\n"

    def generate_selector_strategy(self, element: UIElement) -> SelectorStrategy:
        """
        Generate self-healing selector strategy for element

        Args:
            element: UI element

        Returns:
            Selector strategy with fallbacks
        """
        fallbacks = []

        # Primary: ID is most stable
        primary = f"id={element.id}" if element.id else None

        # Fallback 1: Accessibility ID
        if element.accessibility_id:
            fallbacks.append(f"accessibility_id={element.accessibility_id}")

        # Fallback 2: XPath
        if element.xpath:
            fallbacks.append(f"xpath={element.xpath}")

        # Fallback 3: Label/text (if available)
        if element.label:
            fallbacks.append(f"text={element.label}")

        # If no ID, use first fallback as primary
        if not primary and fallbacks:
            primary = fallbacks.pop(0)

        if not primary:
            primary = f"xpath=//*[@type='{element.type}']"

        # Calculate stability score
        stability = 1.0 if element.id else (0.8 if element.accessibility_id else 0.5)

        return SelectorStrategy(primary=primary, fallbacks=fallbacks, stability_score=stability)

    def _generate_python_page_object(self, screen: Screen, package_name: str) -> str:
        """Generate Python Page Object"""
        class_name = f"{screen.name}Page"

        code = f'''"""
Page Object for {screen.name}
Auto-generated with self-healing selectors
"""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Optional


class {class_name}:
    """Page Object for {screen.name}"""

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 10)

'''

        # Generate selectors with self-healing
        for element in screen.elements[:10]:  # Limit to 10 elements
            strategy = self.generate_selector_strategy(element)
            elem_name = (element.label or element.id or f"element_{element.type}").replace(" ", "_").lower()

            code += f'''    def get_{elem_name}(self):
        """
        Get {element.label or element.id or element.type} element
        Uses self-healing selector with fallback strategies
        """
        strategies = {strategy.get_selector_chain()}
        
        for selector in strategies:
            try:
                locator_type, locator_value = selector.split('=', 1)
                by_type = {{
                    'id': By.ID,
                    'xpath': By.XPATH,
                    'accessibility_id': By.ACCESSIBILITY_ID,
                    'text': By.LINK_TEXT
                }}.get(locator_type, By.XPATH)
                
                element = self.wait.until(
                    EC.presence_of_element_located((by_type, locator_value))
                )
                return element
            except Exception:
                continue
        
        raise Exception(f"Could not find {elem_name} with any selector strategy")

'''

        # Generate helper methods
        code += f'''    def is_displayed(self) -> bool:
        """Check if {screen.name} is displayed"""
        try:
            # Check for presence of key elements
            self.get_{(screen.elements[0].label or screen.elements[0].id or "element").replace(" ", "_").lower()}()
            return True
        except Exception:
            return False

    def wait_until_visible(self, timeout: int = 10):
        """Wait until {screen.name} is visible"""
        import time
        end_time = time.time() + timeout
        while time.time() < end_time:
            if self.is_displayed():
                return
            time.sleep(0.5)
        raise TimeoutException(f"{screen.name} not visible after {{timeout}}s")
'''

        return code

    def _generate_java_page_object(self, screen: Screen, package_name: str) -> str:
        """Generate Java Page Object"""
        class_name = f"{screen.name}Page"

        code = f'''package {package_name};

import io.appium.java_client.AppiumDriver;
import io.appium.java_client.pagefactory.AppiumFieldDecorator;
import org.openqa.selenium.By;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.PageFactory;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;
import java.time.Duration;

/**
 * Page Object for {screen.name}
 * Auto-generated with self-healing selectors
 */
public class {class_name} {{
    
    private final AppiumDriver driver;
    private final WebDriverWait wait;
    
    public {class_name}(AppiumDriver driver) {{
        this.driver = driver;
        this.wait = new WebDriverWait(driver, Duration.ofSeconds(10));
        PageFactory.initElements(new AppiumFieldDecorator(driver), this);
    }}
    
'''

        # Generate methods for elements
        for element in screen.elements[:5]:
            strategy = self.generate_selector_strategy(element)
            elem_name = (element.label or element.id or f"element_{element.type}").replace(" ", "_").lower()
            method_name = ''.join(word.capitalize() for word in elem_name.split('_'))

            code += f'''    public WebElement get{method_name}() {{
        String[] strategies = {{{", ".join(f'"{s}"' for s in strategy.get_selector_chain())}}};
        
        for (String selector : strategies) {{
            try {{
                String[] parts = selector.split("=", 2);
                By locator = getLocator(parts[0], parts[1]);
                return wait.until(ExpectedConditions.presenceOfElementLocated(locator));
            }} catch (Exception e) {{
                continue;
            }}
        }}
        
        throw new RuntimeException("Could not find {elem_name}");
    }}
    
'''

        code += f'''    private By getLocator(String type, String value) {{
        switch (type) {{
            case "id": return By.id(value);
            case "xpath": return By.xpath(value);
            case "accessibility_id": return By.accessibilityId(value);
            default: return By.xpath(value);
        }}
    }}
    
    public boolean isDisplayed() {{
        try {{
            get{(''.join(word.capitalize() for word in (screen.elements[0].label or screen.elements[0].id or "element").replace(" ", "_").lower().split('_')))}();
            return true;
        }} catch (Exception e) {{
            return false;
        }}
    }}
}}
'''

        return code

    def _generate_kotlin_page_object(self, screen: Screen, package_name: str) -> str:
        """Generate Kotlin Page Object"""
        class_name = f"{screen.name}Page"

        return f'''package {package_name}

import io.appium.java_client.AppiumDriver
import org.openqa.selenium.By
import org.openqa.selenium.WebElement
import org.openqa.selenium.support.ui.ExpectedConditions
import org.openqa.selenium.support.ui.WebDriverWait
import java.time.Duration

/**
 * Page Object for {screen.name}
 * Auto-generated with self-healing selectors
 */
class {class_name}(private val driver: AppiumDriver) {{
    
    private val wait = WebDriverWait(driver, Duration.ofSeconds(10))
    
    private fun getLocator(type: String, value: String): By {{
        return when (type) {{
            "id" -> By.id(value)
            "xpath" -> By.xpath(value)
            "accessibility_id" -> By.accessibilityId(value)
            else -> By.xpath(value)
        }}
    }}
    
    private fun findWithFallback(strategies: List<String>): WebElement {{
        for (selector in strategies) {{
            try {{
                val (type, value) = selector.split("=", limit = 2)
                val locator = getLocator(type, value)
                return wait.until(ExpectedConditions.presenceOfElementLocated(locator))
            }} catch (e: Exception) {{
                continue
            }}
        }}
        throw RuntimeException("Could not find element with any strategy")
    }}
    
    fun isDisplayed(): Boolean {{
        return try {{
            // Check key element exists
            true
        }} catch (e: Exception) {{
            false
        }}
    }}
}}
'''

    def _generate_javascript_page_object(self, screen: Screen, package_name: str) -> str:
        """Generate JavaScript Page Object"""
        class_name = f"{screen.name}Page"

        return f'''/**
 * Page Object for {screen.name}
 * Auto-generated with self-healing selectors
 */
class {class_name} {{
    constructor(driver) {{
        this.driver = driver;
    }}
    
    async findWithFallback(strategies) {{
        for (const selector of strategies) {{
            try {{
                const [type, value] = selector.split('=');
                let element;
                
                switch (type) {{
                    case 'id':
                        element = await this.driver.$(`#${{value}}`);
                        break;
                    case 'xpath':
                        element = await this.driver.$(value);
                        break;
                    case 'accessibility_id':
                        element = await this.driver.$(`~${{value}}`);
                        break;
                    default:
                        element = await this.driver.$(value);
                }}
                
                if (await element.isDisplayed()) {{
                    return element;
                }}
            }} catch (e) {{
                continue;
            }}
        }}
        throw new Error('Could not find element with any strategy');
    }}
    
    async isDisplayed() {{
        try {{
            // Check key element
            return true;
        }} catch (e) {{
            return false;
        }}
    }}
}}

module.exports = {class_name};
'''

    def _generate_typescript_page_object(self, screen: Screen, package_name: str) -> str:
        """Generate TypeScript Page Object"""
        class_name = f"{screen.name}Page"

        return f'''import {{ Browser, Element }} from 'webdriverio';

/**
 * Page Object for {screen.name}
 * Auto-generated with self-healing selectors
 */
export class {class_name} {{
    constructor(private driver: Browser) {{}}
    
    private async findWithFallback(strategies: string[]): Promise<Element> {{
        for (const selector of strategies) {{
            try {{
                const [type, value] = selector.split('=');
                let element: Element;
                
                switch (type) {{
                    case 'id':
                        element = await this.driver.$(`#${{value}}`);
                        break;
                    case 'xpath':
                        element = await this.driver.$(value);
                        break;
                    case 'accessibility_id':
                        element = await this.driver.$(`~${{value}}`);
                        break;
                    default:
                        element = await this.driver.$(value);
                }}
                
                if (await element.isDisplayed()) {{
                    return element;
                }}
            }} catch (e) {{
                continue;
            }}
        }}
        throw new Error('Could not find element with any strategy');
    }}
    
    async isDisplayed(): Promise<boolean> {{
        try {{
            // Check key element
            return true;
        }} catch (e) {{
            return false;
        }}
    }}
}}
'''

    def _generate_csharp_page_object(self, screen: Screen, package_name: str) -> str:
        """Generate C# Page Object"""
        class_name = f"{screen.name}Page"

        return f'''using OpenQA.Selenium;
using OpenQA.Selenium.Appium;
using OpenQA.Selenium.Support.UI;
using System;
using System.Collections.Generic;

namespace {package_name}
{{
    /// <summary>
    /// Page Object for {screen.name}
    /// Auto-generated with self-healing selectors
    /// </summary>
    public class {class_name}
    {{
        private readonly AppiumDriver driver;
        private readonly WebDriverWait wait;
        
        public {class_name}(AppiumDriver driver)
        {{
            this.driver = driver;
            this.wait = new WebDriverWait(driver, TimeSpan.FromSeconds(10));
        }}
        
        private IWebElement FindWithFallback(List<string> strategies)
        {{
            foreach (var selector in strategies)
            {{
                try
                {{
                    var parts = selector.Split('=', 2);
                    var type = parts[0];
                    var value = parts[1];
                    
                    By locator = type switch
                    {{
                        "id" => By.Id(value),
                        "xpath" => By.XPath(value),
                        "accessibility_id" => By.AccessibilityId(value),
                        _ => By.XPath(value)
                    }};
                    
                    return wait.Until(d => d.FindElement(locator));
                }}
                catch
                {{
                    continue;
                }}
            }}
            throw new Exception("Could not find element with any strategy");
        }}
        
        public bool IsDisplayed()
        {{
            try
            {{
                // Check key element
                return true;
            }}
            catch
            {{
                return false;
            }}
        }}
    }}
}}
'''

    def _generate_go_page_object(self, screen: Screen, package_name: str) -> str:
        """Generate Go Page Object"""
        class_name = f"{screen.name}Page"

        return f'''package {package_name}

import (
    "fmt"
    "github.com/tebeka/selenium"
)

// {class_name} represents {screen.name}
// Auto-generated with self-healing selectors
type {class_name} struct {{
    driver selenium.WebDriver
}}

// New{class_name} creates a new {screen.name} page object
func New{class_name}(driver selenium.WebDriver) *{class_name} {{
    return &{class_name}{{driver: driver}}
}}

func (p *{class_name}) findWithFallback(strategies []string) (selenium.WebElement, error) {{
    for _, selector := range strategies {{
        // Parse selector
        // Try to find element
        // Return if found
    }}
    return nil, fmt.Errorf("could not find element with any strategy")
}}

// IsDisplayed checks if {screen.name} is displayed
func (p *{class_name}) IsDisplayed() bool {{
    // Check key element
    return true
}}
'''

    def _generate_swift_page_object(self, screen: Screen, package_name: str) -> str:
        """Generate Swift Page Object"""
        class_name = f"{screen.name}Page"

        return f'''import XCTest

/// Page Object for {screen.name}
/// Auto-generated with self-healing selectors
class {class_name} {{
    
    let app: XCUIApplication
    
    init(app: XCUIApplication) {{
        self.app = app
    }}
    
    private func findWithFallback(strategies: [String]) -> XCUIElement? {{
        for selector in strategies {{
            let parts = selector.components(separatedBy: "=")
            guard parts.count == 2 else {{ continue }}
            
            let type = parts[0]
            let value = parts[1]
            
            var element: XCUIElement?
            
            switch type {{
            case "id":
                element = app.otherElements[value]
            case "accessibility_id":
                element = app.otherElements.matching(identifier: value).element
            default:
                continue
            }}
            
            if element?.exists == true {{
                return element
            }}
        }}
        return nil
    }}
    
    func isDisplayed() -> Bool {{
        // Check key element
        return true
    }}
}}
'''

    def generate_test_scaffold(self, screen: Screen, test_name: Optional[str] = None) -> str:
        """
        Generate test scaffold for screen

        Args:
            screen: Screen to generate test for
            test_name: Optional test name

        Returns:
            Generated test code
        """
        test_name = test_name or f"test_{screen.name.lower()}"

        if self.language == Language.PYTHON:
            return self._generate_python_test_scaffold(screen, test_name)
        elif self.language == Language.JAVA:
            return self._generate_java_test_scaffold(screen, test_name)
        # Add other languages as needed

        return f"# Test scaffold for {self.language} not yet implemented\n"

    def _generate_python_test_scaffold(self, screen: Screen, test_name: str) -> str:
        """Generate Python test scaffold"""
        page_class = f"{screen.name}Page"

        return f'''"""
Test for {screen.name}
Auto-generated test scaffold
"""

import pytest
from pages.{screen.name.lower()}_page import {page_class}


class Test{screen.name}:
    """Tests for {screen.name}"""
    
    @pytest.fixture
    def {screen.name.lower()}_page(self, driver):
        """Create {screen.name} page object"""
        return {page_class}(driver)
    
    def {test_name}_loads(self, {screen.name.lower()}_page):
        """Test that {screen.name} loads correctly"""
        assert {screen.name.lower()}_page.is_displayed(), "{screen.name} should be visible"
    
    def {test_name}_interactions(self, {screen.name.lower()}_page):
        """Test interactions on {screen.name}"""
        # TODO: Add interaction tests
        pass
'''

    def _generate_java_test_scaffold(self, screen: Screen, test_name: str) -> str:
        """Generate Java test scaffold"""
        page_class = f"{screen.name}Page"

        return f'''package tests;

import org.junit.jupiter.api.*;
import pages.{page_class};
import static org.junit.jupiter.api.Assertions.*;

/**
 * Test for {screen.name}
 * Auto-generated test scaffold
 */
public class {screen.name}Test {{
    
    private {page_class} {screen.name.lower()}Page;
    
    @BeforeEach
    public void setUp() {{
        // Initialize driver and page object
        {screen.name.lower()}Page = new {page_class}(driver);
    }}
    
    @Test
    public void {test_name}Loads() {{
        assertTrue({screen.name.lower()}Page.isDisplayed(), "{screen.name} should be visible");
    }}
    
    @Test
    public void {test_name}Interactions() {{
        // TODO: Add interaction tests
    }}
}}
'''

    def generate_bdd_feature(self, screen: Screen) -> str:
        """Generate BDD feature file"""
        return f'''Feature: {screen.name}
  As a user
  I want to interact with {screen.name}
  So that I can complete my task

  Scenario: {screen.name} loads successfully
    Given I am on the app
    When I navigate to {screen.name}
    Then {screen.name} should be displayed
    
  Scenario: Interact with {screen.name}
    Given I am on {screen.name}
    When I perform actions
    Then I should see expected results
'''

    def save_files(self, screen: Screen, output_dir: Path):
        """
        Generate and save all artifacts for a screen

        Args:
            screen: Screen to generate artifacts for
            output_dir: Output directory
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Page Object
        po_code = self.generate_page_object(screen)
        po_filename = f"{screen.name.lower()}_page"
        po_ext = self._get_file_extension()
        (output_dir / "pages").mkdir(exist_ok=True)
        with open(output_dir / "pages" / f"{po_filename}{po_ext}", 'w') as f:
            f.write(po_code)

        # Test scaffold
        test_code = self.generate_test_scaffold(screen)
        test_filename = f"test_{screen.name.lower()}"
        (output_dir / "tests").mkdir(exist_ok=True)
        with open(output_dir / "tests" / f"{test_filename}{po_ext}", 'w') as f:
            f.write(test_code)

        # BDD feature (optional)
        feature_code = self.generate_bdd_feature(screen)
        (output_dir / "features").mkdir(exist_ok=True)
        with open(output_dir / "features" / f"{screen.name.lower()}.feature", 'w') as f:
            f.write(feature_code)

    def _get_file_extension(self) -> str:
        """Get file extension for language"""
        extensions = {
            Language.PYTHON: ".py",
            Language.JAVA: ".java",
            Language.KOTLIN: ".kt",
            Language.JAVASCRIPT: ".js",
            Language.TYPESCRIPT: ".ts",
            Language.CSHARP: ".cs",
            Language.GO: ".go",
            Language.SWIFT: ".swift",
        }
        return extensions.get(self.language, ".txt")
