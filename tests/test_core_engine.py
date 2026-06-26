"""
Unit tests for STEP 1: Core Engine

Tests UI discovery, flow graph building, and multi-language test generation.
"""

import json

import pytest

from framework.core.engine import (
    CoreEngine, UIElement, Screen, Language
)


class TestUIElement:
    """Test UIElement class"""

    def test_create_ui_element(self):
        """Test UIElement creation"""
        elem = UIElement(
            id="login_button",
            type="button",
            label="Login",
            xpath="//android.widget.Button[@text='Login']",
            accessibility_id="login_btn",
            bounds={'x': 100, 'y': 200, 'width': 50, 'height': 30},
            visible=True,
            enabled=True
        )

        assert elem.id == "login_button"
        assert elem.type == "button"
        assert elem.visible
        assert elem.enabled

    def test_python_selector_generation(self):
        """Test Python selector generation"""
        elem = UIElement(
            id="test_id",
            type="button",
            label="Test",
            xpath="//button",
            accessibility_id=None,
            bounds={},
            visible=True,
            enabled=True
        )

        selector = elem.to_selector(Language.PYTHON)
        assert 'driver.find_element' in selector
        assert 'test_id' in selector

    def test_java_selector_generation(self):
        """Test Java selector generation"""
        elem = UIElement(
            id="test_id",
            type="button",
            label="Test",
            xpath="//button",
            accessibility_id=None,
            bounds={},
            visible=True,
            enabled=True
        )

        selector = elem.to_selector(Language.JAVA)
        assert 'driver.findElement' in selector
        assert 'test_id' in selector

    def test_kotlin_selector_generation(self):
        """Test Kotlin selector generation"""
        elem = UIElement(
            id="test_id",
            type="button",
            label="Test",
            xpath="//button",
            accessibility_id=None,
            bounds={},
            visible=True,
            enabled=True
        )

        selector = elem.to_selector(Language.KOTLIN)
        assert 'driver.findElement' in selector


class TestScreen:
    """Test Screen class"""

    def test_create_screen(self):
        """Test Screen creation"""
        elements = [
            UIElement("id1", "button", "Button 1", None, None, {}, True, True),
            UIElement("id2", "textfield", "Text", None, None, {}, True, True),
        ]

        screen = Screen(
            id="screen1",
            name="LoginScreen",
            elements=elements,
            transitions=[],
            api_calls=[]
        )

        assert screen.id == "screen1"
        assert len(screen.elements) == 2

    def test_find_interactive_elements(self):
        """Test finding interactive elements"""
        elements = [
            UIElement("btn1", "button", "Button", None, None, {}, True, True),
            UIElement("txt1", "textfield", "Text", None, None, {}, True, True),
            UIElement("lbl1", "label", "Label", None, None, {}, True, False),  # Not enabled
        ]

        screen = Screen("s1", "Test", elements, [], [])
        interactive = screen.find_interactive_elements()

        assert len(interactive) == 2
        assert all(e.enabled for e in interactive)


class TestCoreEngine:
    """Test CoreEngine class"""

    def test_engine_initialization(self):
        """Test engine initializes correctly"""
        engine = CoreEngine()

        assert 'ui_discovery' in engine.enabled_modules
        assert 'flow_builder' in engine.enabled_modules
        assert 'skeleton_generator' in engine.enabled_modules

    def test_engine_custom_config(self):
        """Test engine with custom config"""
        config = {
            'enabled_modules': ['ui_discovery']
        }
        engine = CoreEngine(config)

        assert engine.enabled_modules == ['ui_discovery']

    def test_discover_ui(self):
        """Test UI discovery"""
        engine = CoreEngine()

        source = {
            'id': 'login_screen',
            'name': 'LoginScreen',
            'elements': [
                {
                    'id': 'username_field',
                    'type': 'textfield',
                    'label': 'Username',
                    'visible': True,
                    'enabled': True,
                    'bounds': {'x': 0, 'y': 0, 'width': 100, 'height': 50}
                },
                {
                    'id': 'password_field',
                    'type': 'textfield',
                    'label': 'Password',
                    'visible': True,
                    'enabled': True,
                    'bounds': {'x': 0, 'y': 60, 'width': 100, 'height': 50}
                },
                {
                    'id': 'login_button',
                    'type': 'button',
                    'label': 'Login',
                    'visible': True,
                    'enabled': True,
                    'bounds': {'x': 0, 'y': 120, 'width': 100, 'height': 40}
                }
            ]
        }

        screen = engine.discover_ui(source)

        assert screen.id == 'login_screen'
        assert screen.name == 'LoginScreen'
        assert len(screen.elements) == 3
        assert screen in engine.screens.values()

    def test_build_flow_graph(self):
        """Test flow graph building"""
        engine = CoreEngine()

        # Create screens
        screen1 = Screen("s1", "Login", [], [], [])
        screen2 = Screen("s2", "Home", [], [], [])
        engine.screens['s1'] = screen1
        engine.screens['s2'] = screen2

        # Build flow
        engine.build_flow_graph("s1", "s2", "click_login")

        assert "s1" in engine.flow_graph
        assert any(f['to'] == "s2" for f in engine.flow_graph["s1"])
        assert "s2" in screen1.transitions

    def test_flow_builder_disabled(self):
        """Test flow builder when disabled"""
        config = {'enabled_modules': ['ui_discovery']}
        engine = CoreEngine(config)

        engine.build_flow_graph("s1", "s2", "action")

        # Should not build graph when disabled
        assert "s1" not in engine.flow_graph

    def test_generate_python_skeleton(self):
        """Test Python skeleton generation"""
        engine = CoreEngine()

        elements = [
            UIElement("btn1", "button", "Login", "//button", None, {}, True, True),
            UIElement("txt1", "textfield", "Username", "//input", None, {}, True, True),
        ]
        screen = Screen("login", "LoginScreen", elements, [], [])

        code = engine.generate_skeleton_test(screen, Language.PYTHON)

        assert "class TestLoginScreen" in code
        assert "def test_" in code
        assert "pytest" in code

    def test_generate_java_skeleton(self):
        """Test Java skeleton generation"""
        engine = CoreEngine()

        elements = [UIElement("btn1", "button", "Test", None, None, {}, True, True)]
        screen = Screen("test", "TestScreen", elements, [], [])

        code = engine.generate_skeleton_test(screen, Language.JAVA)

        assert "public class TestScreenTest" in code
        assert "@Test" in code
        assert "junit" in code.lower()

    def test_generate_kotlin_skeleton(self):
        """Test Kotlin skeleton generation"""
        engine = CoreEngine()

        elements = [UIElement("btn1", "button", "Test", None, None, {}, True, True)]
        screen = Screen("test", "TestScreen", elements, [], [])

        code = engine.generate_skeleton_test(screen, Language.KOTLIN)

        assert "class TestScreenTest" in code
        assert "@Test" in code

    def test_generate_javascript_skeleton(self):
        """Test JavaScript skeleton generation"""
        engine = CoreEngine()

        elements = [UIElement("btn1", "button", "Test", None, None, {}, True, True)]
        screen = Screen("test", "TestScreen", elements, [], [])

        code = engine.generate_skeleton_test(screen, Language.JAVASCRIPT)

        assert "describe(" in code
        assert "it(" in code

    def test_generate_typescript_skeleton(self):
        """Test TypeScript skeleton generation"""
        engine = CoreEngine()

        elements = [UIElement("btn1", "button", "Test", None, None, {}, True, True)]
        screen = Screen("test", "TestScreen", elements, [], [])

        code = engine.generate_skeleton_test(screen, Language.TYPESCRIPT)

        assert "describe(" in code
        assert "WebdriverIO" in code

    def test_generate_csharp_skeleton(self):
        """Test C# skeleton generation"""
        engine = CoreEngine()

        elements = [UIElement("btn1", "button", "Test", None, None, {}, True, True)]
        screen = Screen("test", "TestScreen", elements, [], [])

        code = engine.generate_skeleton_test(screen, Language.CSHARP)

        assert "public class TestScreenTest" in code
        assert "[Test]" in code
        assert "NUnit" in code

    def test_generate_go_skeleton(self):
        """Test Go skeleton generation"""
        engine = CoreEngine()

        elements = [UIElement("btn1", "button", "Test", None, None, {}, True, True)]
        screen = Screen("test", "TestScreen", elements, [], [])

        code = engine.generate_skeleton_test(screen, Language.GO)

        assert "func Test" in code
        assert "testing.T" in code

    def test_generate_swift_skeleton(self):
        """Test Swift skeleton generation"""
        engine = CoreEngine()

        elements = [UIElement("btn1", "button", "Test", None, None, {}, True, True)]
        screen = Screen("test", "TestScreen", elements, [], [])

        code = engine.generate_skeleton_test(screen, Language.SWIFT)

        assert "class TestScreenTest" in code
        assert "XCTest" in code
        assert "func test" in code

    def test_skeleton_generator_disabled(self):
        """Test skeleton generation when disabled"""
        config = {'enabled_modules': ['ui_discovery']}
        engine = CoreEngine(config)

        elements = [UIElement("btn1", "button", "Test", None, None, {}, True, True)]
        screen = Screen("test", "Test", elements, [], [])

        code = engine.generate_skeleton_test(screen, Language.PYTHON)

        assert "disabled" in code.lower()

    def test_export_flow_graph(self, tmp_path):
        """Test flow graph export"""
        engine = CoreEngine()

        # Create test data
        screen1 = Screen("s1", "Login", [], ["s2"], [])
        screen2 = Screen("s2", "Home", [], [], [])
        engine.screens['s1'] = screen1
        engine.screens['s2'] = screen2
        engine.flow_graph['s1'] = [{'to': 's2', 'action': 'login'}]

        # Export
        output = tmp_path / "flow.json"
        engine.export_flow_graph(output)

        # Verify
        assert output.exists()
        with open(output) as f:
            data = json.load(f)

        assert 'screens' in data
        assert 'flow' in data
        assert 's1' in data['screens']
        assert data['screens']['s1']['name'] == 'Login'


class TestMultiLanguageSupport:
    """Test multi-language selector generation"""

    @pytest.fixture
    def sample_element(self):
        """Sample UI element"""
        return UIElement(
            id="test_button",
            type="button",
            label="Test",
            xpath="//button[@id='test_button']",
            accessibility_id="test_btn",
            bounds={'x': 0, 'y': 0, 'width': 100, 'height': 50},
            visible=True,
            enabled=True
        )

    def test_all_languages_generate_selectors(self, sample_element):
        """Test all supported languages generate valid selectors"""
        for lang in Language:
            selector = sample_element.to_selector(lang)
            assert selector
            assert len(selector) > 0
            assert "Unsupported" not in selector
