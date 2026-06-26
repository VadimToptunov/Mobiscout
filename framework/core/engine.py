"""
STEP 1: Core Engine - Extended UI Discovery with Multi-Language Support

This module extends the existing UI discovery with:
- Multi-language test generation (Python, Java, Kotlin, JS, TS, C#, Go, Swift)
- Error handling and recovery
- Configurable enable/disable
- Flow graph building
- Skeleton test generation
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional


class Language(Enum):
    """Supported programming languages"""
    PYTHON = "python"
    JAVA = "java"
    KOTLIN = "kotlin"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    CSHARP = "csharp"
    GO = "go"
    SWIFT = "swift"


@dataclass
class UIElement:
    """Discovered UI element with multi-language selector support"""
    id: str
    type: str
    label: Optional[str]
    xpath: Optional[str]
    accessibility_id: Optional[str]
    bounds: Dict[str, int]
    visible: bool
    enabled: bool

    def to_selector(self, language: Language) -> str:
        """Generate language-specific selector"""
        if language == Language.PYTHON:
            if self.id:
                return f'driver.find_element(By.ID, "{self.id}")'
            return f'driver.find_element(By.XPATH, "{self.xpath}")'

        elif language == Language.JAVA:
            if self.id:
                return f'driver.findElement(By.id("{self.id}"))'
            return f'driver.findElement(By.xpath("{self.xpath}"))'

        elif language == Language.KOTLIN:
            if self.id:
                return f'driver.findElement(By.id("{self.id}"))'
            return f'driver.findElement(By.xpath("{self.xpath}"))'

        elif language == Language.JAVASCRIPT:
            if self.id:
                return f'await driver.findElement({{"id": "{self.id}"}})'
            return f'await driver.findElement({{"xpath": "{self.xpath}"}})'

        elif language == Language.TYPESCRIPT:
            if self.id:
                return f'await driver.findElement(By.ID, "{self.id}")'
            return f'await driver.findElement(By.XPATH, "{self.xpath}")'

        elif language == Language.CSHARP:
            if self.id:
                return f'driver.FindElement(By.Id("{self.id}"))'
            return f'driver.FindElement(By.XPath("{self.xpath}"))'

        elif language == Language.GO:
            if self.id:
                return f'driver.FindElement(selenium.ByID, "{self.id}")'
            return f'driver.FindElement(selenium.ByXPATH, "{self.xpath}")'

        elif language == Language.SWIFT:
            if self.id:
                return f'app.otherElements["{self.id}"]'
            return f'app.otherElements.matching(identifier: "{self.id}").element'

        return f"# Unsupported language: {language}"


@dataclass
class Screen:
    """Discovered screen with elements and flow connections"""
    id: str
    name: str
    elements: List[UIElement]
    transitions: List[str]  # Screen IDs this can transition to
    api_calls: List[Dict[str, Any]]  # API calls made on this screen

    def find_interactive_elements(self) -> List[UIElement]:
        """Find elements that can be interacted with"""
        return [e for e in self.elements
                if e.enabled and e.type in ('button', 'textfield', 'switch')]


class CoreEngine:
    """
    STEP 1: Core Engine - Extended with multi-language support

    Features:
    - UI Discovery across multiple screens
    - Flow graph building (screen → action → screen)
    - Multi-language selector generation
    - Error handling and recovery
    - Configurable modules
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.screens: Dict[str, Screen] = {}
        self.flow_graph: Dict[str, List[Dict[str, str]]] = {}
        self.enabled_modules = self.config.get('enabled_modules', [
            'ui_discovery', 'flow_builder', 'skeleton_generator'
        ])

    def discover_ui(self, source: Dict[str, Any]) -> Screen:
        """
        Discover UI elements from page source

        Args:
            source: Page source dictionary with hierarchy

        Returns:
            Screen object with discovered elements
        """
        screen_id = source.get('id', f'screen_{len(self.screens)}')
        screen_name = source.get('name', f'Screen{len(self.screens)}')

        elements = []
        for elem_data in source.get('elements', []):
            element = UIElement(
                id=elem_data.get('id', ''),
                type=elem_data.get('type', 'unknown'),
                label=elem_data.get('label'),
                xpath=elem_data.get('xpath'),
                accessibility_id=elem_data.get('accessibilityId'),
                bounds=elem_data.get('bounds', {}),
                visible=elem_data.get('visible', True),
                enabled=elem_data.get('enabled', True),
            )
            elements.append(element)

        screen = Screen(
            id=screen_id,
            name=screen_name,
            elements=elements,
            transitions=[],
            api_calls=[]
        )

        self.screens[screen_id] = screen
        return screen

    def build_flow_graph(self, from_screen: str, to_screen: str, action: str):
        """
        Build flow graph: screen → action → next_screen

        Args:
            from_screen: Source screen ID
            to_screen: Destination screen ID
            action: Action that caused transition
        """
        if 'flow_builder' not in self.enabled_modules:
            return

        if from_screen not in self.flow_graph:
            self.flow_graph[from_screen] = []

        self.flow_graph[from_screen].append({
            'to': to_screen,
            'action': action
        })

        # Update screen transitions
        if from_screen in self.screens:
            screen = self.screens[from_screen]
            if to_screen not in screen.transitions:
                screen.transitions.append(to_screen)

    def generate_skeleton_test(self, screen: Screen, language: Language) -> str:
        """
        Generate skeleton test for screen in specified language

        Args:
            screen: Screen to generate test for
            language: Target programming language

        Returns:
            Generated test code
        """
        if 'skeleton_generator' not in self.enabled_modules:
            return f"# Skeleton generator disabled\n"

        if language == Language.PYTHON:
            return self._generate_python_test(screen)
        elif language == Language.JAVA:
            return self._generate_java_test(screen)
        elif language == Language.KOTLIN:
            return self._generate_kotlin_test(screen)
        elif language == Language.JAVASCRIPT:
            return self._generate_javascript_test(screen)
        elif language == Language.TYPESCRIPT:
            return self._generate_typescript_test(screen)
        elif language == Language.CSHARP:
            return self._generate_csharp_test(screen)
        elif language == Language.GO:
            return self._generate_go_test(screen)
        elif language == Language.SWIFT:
            return self._generate_swift_test(screen)

        return f"# Language {language} not yet supported\n"

    def _generate_python_test(self, screen: Screen) -> str:
        """Generate Python/Pytest test"""
        code = f'''"""Test for {screen.name}"""
import pytest
from selenium.webdriver.common.by import By

class Test{screen.name}:
    """Tests for {screen.name} screen"""
    
    def test_{screen.name.lower()}_loads(self, driver):
        """Test that {screen.name} loads"""
        # TODO: Add navigation
        assert driver.current_activity  # Placeholder
    
'''
        for element in screen.find_interactive_elements()[:3]:  # First 3 elements
            elem_name = (element.label or element.id or 'element').replace(' ', '_').lower()
            code += f'''    def test_{elem_name}_visible(self, driver):
        """Test {element.label or element.id} is visible"""
        elem = {element.to_selector(Language.PYTHON)}
        assert elem.is_displayed()
    
'''
        return code

    def _generate_java_test(self, screen: Screen) -> str:
        """Generate Java/JUnit test"""
        return f'''package com.tests;

import org.junit.jupiter.api.*;
import io.appium.java_client.AppiumDriver;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Test for {screen.name}
 */
public class {screen.name}Test {{
    
    private AppiumDriver driver;
    
    @BeforeEach
    public void setUp() {{
        // TODO: Initialize driver
    }}
    
    @Test
    public void test{screen.name}Loads() {{
        // TODO: Navigate to screen
        assertNotNull(driver.getCurrentActivity());
    }}
}}
'''

    def _generate_kotlin_test(self, screen: Screen) -> str:
        """Generate Kotlin test"""
        return f'''package com.tests

import org.junit.jupiter.api.*
import io.appium.java_client.AppiumDriver
import org.junit.jupiter.api.Assertions.*

/**
 * Test for {screen.name}
 */
class {screen.name}Test {{
    
    private lateinit var driver: AppiumDriver
    
    @BeforeEach
    fun setUp() {{
        // TODO: Initialize driver
    }}
    
    @Test
    fun `{screen.name} loads correctly`() {{
        // TODO: Navigate to screen
        assertNotNull(driver.currentActivity)
    }}
}}
'''

    def _generate_javascript_test(self, screen: Screen) -> str:
        """Generate JavaScript test"""
        return f'''// Test for {screen.name}
const {{ remote }} = require('webdriverio');

describe('{screen.name} Tests', () => {{
    let driver;
    
    before(async () => {{
        // TODO: Initialize driver
    }});
    
    it('should load {screen.name}', async () => {{
        // TODO: Navigate to screen
        const activity = await driver.getCurrentActivity();
        expect(activity).toBeTruthy();
    }});
}});
'''

    def _generate_typescript_test(self, screen: Screen) -> str:
        """Generate TypeScript test"""
        return f'''// Test for {screen.name}
import {{ remote }} from 'webdriverio';

describe('{screen.name} Tests', () => {{
    let driver: WebdriverIO.Browser;
    
    before(async () => {{
        // TODO: Initialize driver
    }});
    
    it('should load {screen.name}', async () => {{
        // TODO: Navigate to screen
        const activity = await driver.getCurrentActivity();
        expect(activity).toBeTruthy();
    }});
}});
'''

    def _generate_csharp_test(self, screen: Screen) -> str:
        """Generate C# test"""
        return f'''using NUnit.Framework;
using OpenQA.Selenium.Appium;

namespace Tests
{{
    /// <summary>
    /// Test for {screen.name}
    /// </summary>
    [TestFixture]
    public class {screen.name}Test
    {{
        private AppiumDriver driver;
        
        [SetUp]
        public void SetUp()
        {{
            // TODO: Initialize driver
        }}
        
        [Test]
        public void Test{screen.name}Loads()
        {{
            // TODO: Navigate to screen
            Assert.IsNotNull(driver.CurrentActivity);
        }}
    }}
}}
'''

    def _generate_go_test(self, screen: Screen) -> str:
        """Generate Go test"""
        return f'''package tests

import (
    "testing"
    "github.com/tebeka/selenium"
)

// Test{screen.name}Loads tests that {screen.name} loads
func Test{screen.name}Loads(t *testing.T) {{
    // TODO: Initialize driver
    // TODO: Navigate to screen
    
    activity, err := driver.CurrentActivity()
    if err != nil {{
        t.Fatal(err)
    }}
    
    if activity == "" {{
        t.Error("Activity should not be empty")
    }}
}}
'''

    def _generate_swift_test(self, screen: Screen) -> str:
        """Generate Swift/XCTest"""
        return f'''import XCTest

/// Test for {screen.name}
class {screen.name}Test: XCTestCase {{
    
    var app: XCUIApplication!
    
    override func setUp() {{
        super.setUp()
        app = XCUIApplication()
        app.launch()
    }}
    
    func test{screen.name}Loads() {{
        // TODO: Navigate to screen
        XCTAssertTrue(app.otherElements.count > 0)
    }}
}}
'''

    def export_flow_graph(self, output_path: Path):
        """Export flow graph to JSON"""
        with open(output_path, 'w') as f:
            json.dump({
                'screens': {sid: {
                    'name': s.name,
                    'transitions': s.transitions,
                    'element_count': len(s.elements)
                } for sid, s in self.screens.items()},
                'flow': self.flow_graph
            }, f, indent=2)
