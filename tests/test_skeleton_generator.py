"""
Unit tests for STEP 3: Skeleton Test Generator

Tests page object generation, self-healing selectors, and test scaffolds.
"""

import pytest

from framework.core.engine import Language, Screen, UIElement
from framework.generators.skeleton_generator import (
    SkeletonTestGenerator,
    PageObjectPattern,
    SelectorStrategy
)


class TestSelectorStrategy:
    """Test SelectorStrategy"""

    def test_create_strategy(self):
        """Test creating selector strategy"""
        strategy = SelectorStrategy(
            primary="id=login_button",
            fallbacks=["accessibility_id=login_btn", "xpath=//button"],
            stability_score=0.9
        )

        assert strategy.primary == "id=login_button"
        assert len(strategy.fallbacks) == 2
        assert strategy.stability_score == 0.9

    def test_get_selector_chain(self):
        """Test getting selector chain"""
        strategy = SelectorStrategy(
            primary="id=test",
            fallbacks=["xpath=//test", "text=Test"]
        )

        chain = strategy.get_selector_chain()

        assert len(chain) == 3
        assert chain[0] == "id=test"
        assert chain[1] == "xpath=//test"
        assert chain[2] == "text=Test"


class TestSkeletonTestGenerator:
    """Test SkeletonTestGenerator"""

    @pytest.fixture
    def sample_screen(self):
        """Create sample screen"""
        elements = [
            UIElement(
                id="username_field",
                type="textfield",
                label="Username",
                xpath="//input[@id='username_field']",
                accessibility_id="username_input",
                bounds={'x': 0, 'y': 0, 'width': 200, 'height': 40},
                visible=True,
                enabled=True
            ),
            UIElement(
                id="password_field",
                type="textfield",
                label="Password",
                xpath="//input[@id='password_field']",
                accessibility_id="password_input",
                bounds={'x': 0, 'y': 50, 'width': 200, 'height': 40},
                visible=True,
                enabled=True
            ),
            UIElement(
                id="login_button",
                type="button",
                label="Login",
                xpath="//button[@id='login_button']",
                accessibility_id="login_btn",
                bounds={'x': 0, 'y': 100, 'width': 200, 'height': 50},
                visible=True,
                enabled=True
            )
        ]

        return Screen(
            id="login_screen",
            name="LoginScreen",
            elements=elements,
            transitions=["home_screen"],
            api_calls=[]
        )

    def test_generator_creation(self):
        """Test creating generator"""
        generator = SkeletonTestGenerator(
            language=Language.PYTHON,
            pattern=PageObjectPattern.CLASSIC
        )

        assert generator.language == Language.PYTHON
        assert generator.pattern == PageObjectPattern.CLASSIC

    def test_generate_selector_strategy_with_id(self):
        """Test generating selector strategy for element with ID"""
        generator = SkeletonTestGenerator(Language.PYTHON)

        element = UIElement(
            id="test_button",
            type="button",
            label="Test",
            xpath="//button",
            accessibility_id="test_btn",
            bounds={},
            visible=True,
            enabled=True
        )

        strategy = generator.generate_selector_strategy(element)

        assert strategy.primary == "id=test_button"
        assert "accessibility_id=test_btn" in strategy.fallbacks
        assert strategy.stability_score == 1.0

    def test_generate_selector_strategy_without_id(self):
        """Test generating selector strategy for element without ID"""
        generator = SkeletonTestGenerator(Language.PYTHON)

        element = UIElement(
            id="",
            type="button",
            label="Test",
            xpath="//button[@text='Test']",
            accessibility_id="test_btn",
            bounds={},
            visible=True,
            enabled=True
        )

        strategy = generator.generate_selector_strategy(element)

        assert "accessibility_id=test_btn" in strategy.primary
        assert strategy.stability_score == 0.8

    def test_generate_python_page_object(self, sample_screen):
        """Test generating Python page object"""
        generator = SkeletonTestGenerator(Language.PYTHON)
        code = generator.generate_page_object(sample_screen)

        assert "class LoginScreenPage" in code
        assert "def get_username" in code
        assert "def get_password" in code
        assert "def get_login" in code
        assert "selenium.webdriver" in code
        assert "self-healing" in code

    def test_generate_java_page_object(self, sample_screen):
        """Test generating Java page object"""
        generator = SkeletonTestGenerator(Language.JAVA)
        code = generator.generate_page_object(sample_screen, "com.example.pages")

        assert "public class LoginScreenPage" in code
        assert "package com.example.pages" in code
        assert "AppiumDriver" in code
        assert "WebDriverWait" in code

    def test_generate_kotlin_page_object(self, sample_screen):
        """Test generating Kotlin page object"""
        generator = SkeletonTestGenerator(Language.KOTLIN)
        code = generator.generate_page_object(sample_screen, "com.example.pages")

        assert "class LoginScreenPage" in code
        assert "package com.example.pages" in code
        assert "AppiumDriver" in code

    def test_generate_javascript_page_object(self, sample_screen):
        """Test generating JavaScript page object"""
        generator = SkeletonTestGenerator(Language.JAVASCRIPT)
        code = generator.generate_page_object(sample_screen)

        assert "class LoginScreenPage" in code
        assert "async findWithFallback" in code
        assert "module.exports" in code

    def test_generate_typescript_page_object(self, sample_screen):
        """Test generating TypeScript page object"""
        generator = SkeletonTestGenerator(Language.TYPESCRIPT)
        code = generator.generate_page_object(sample_screen)

        assert "export class LoginScreenPage" in code
        assert "Browser" in code
        assert "Element" in code

    def test_generate_csharp_page_object(self, sample_screen):
        """Test generating C# page object"""
        generator = SkeletonTestGenerator(Language.CSHARP)
        code = generator.generate_page_object(sample_screen, "TestProject.Pages")

        assert "public class LoginScreenPage" in code
        assert "namespace TestProject.Pages" in code
        assert "AppiumDriver" in code

    def test_generate_go_page_object(self, sample_screen):
        """Test generating Go page object"""
        generator = SkeletonTestGenerator(Language.GO)
        code = generator.generate_page_object(sample_screen, "pages")

        assert "package pages" in code
        assert "type LoginScreenPage struct" in code
        assert "func NewLoginScreenPage" in code

    def test_generate_swift_page_object(self, sample_screen):
        """Test generating Swift page object"""
        generator = SkeletonTestGenerator(Language.SWIFT)
        code = generator.generate_page_object(sample_screen)

        assert "class LoginScreenPage" in code
        assert "XCUIApplication" in code
        assert "func isDisplayed" in code

    def test_generate_python_test_scaffold(self, sample_screen):
        """Test generating Python test scaffold"""
        generator = SkeletonTestGenerator(Language.PYTHON)
        code = generator.generate_test_scaffold(sample_screen)

        assert "class TestLoginScreen" in code
        assert "pytest" in code
        assert "def test_" in code
        assert "LoginScreenPage" in code

    def test_generate_java_test_scaffold(self, sample_screen):
        """Test generating Java test scaffold"""
        generator = SkeletonTestGenerator(Language.JAVA)
        code = generator.generate_test_scaffold(sample_screen)

        assert "public class LoginScreenTest" in code
        assert "@Test" in code
        assert "@BeforeEach" in code

    def test_generate_bdd_feature(self, sample_screen):
        """Test generating BDD feature file"""
        generator = SkeletonTestGenerator(Language.PYTHON)
        feature = generator.generate_bdd_feature(sample_screen)

        assert "Feature: LoginScreen" in feature
        assert "Scenario:" in feature
        assert "Given" in feature
        assert "When" in feature
        assert "Then" in feature

    def test_file_extension_mapping(self):
        """Test file extension mapping"""
        extensions = {
            Language.PYTHON: ".py",
            Language.JAVA: ".java",
            Language.KOTLIN: ".kt",
            Language.JAVASCRIPT: ".js",
            Language.TYPESCRIPT: ".ts",
            Language.CSHARP: ".cs",
            Language.GO: ".go",
            Language.SWIFT: ".swift"
        }

        for lang, expected_ext in extensions.items():
            generator = SkeletonTestGenerator(lang)
            assert generator._get_file_extension() == expected_ext

    def test_save_files(self, sample_screen, tmp_path):
        """Test saving all generated files"""
        generator = SkeletonTestGenerator(Language.PYTHON)
        generator.save_files(sample_screen, tmp_path)

        # Check that directories were created
        assert (tmp_path / "pages").exists()
        assert (tmp_path / "tests").exists()
        assert (tmp_path / "features").exists()

        # Check that files were created
        assert (tmp_path / "pages" / "loginscreen_page.py").exists()
        assert (tmp_path / "tests" / "test_loginscreen.py").exists()
        assert (tmp_path / "features" / "loginscreen.feature").exists()

    def test_save_files_creates_content(self, sample_screen, tmp_path):
        """Test that saved files contain expected content"""
        generator = SkeletonTestGenerator(Language.PYTHON)
        generator.save_files(sample_screen, tmp_path)

        # Read and verify page object
        with open(tmp_path / "pages" / "loginscreen_page.py") as f:
            po_content = f.read()
            assert "class LoginScreenPage" in po_content
            assert "get_username" in po_content

        # Read and verify test
        with open(tmp_path / "tests" / "test_loginscreen.py") as f:
            test_content = f.read()
            assert "class TestLoginScreen" in test_content

        # Read and verify feature
        with open(tmp_path / "features" / "loginscreen.feature") as f:
            feature_content = f.read()
            assert "Feature: LoginScreen" in feature_content


class TestPageObjectPatterns:
    """Test different page object patterns"""

    @pytest.fixture
    def simple_screen(self):
        """Simple screen for testing"""
        elements = [
            UIElement("btn1", "button", "Click", None, None, {}, True, True)
        ]
        return Screen("simple", "SimpleScreen", elements, [], [])

    def test_classic_pattern(self, simple_screen):
        """Test classic page object pattern"""
        generator = SkeletonTestGenerator(
            Language.PYTHON,
            pattern=PageObjectPattern.CLASSIC
        )

        code = generator.generate_page_object(simple_screen)

        assert "class SimpleScreenPage" in code
        assert "def get_click" in code

    def test_screenplay_pattern(self, simple_screen):
        """Test screenplay pattern (placeholder)"""
        generator = SkeletonTestGenerator(
            Language.PYTHON,
            pattern=PageObjectPattern.SCREENPLAY
        )

        # For now, it uses classic pattern
        code = generator.generate_page_object(simple_screen)
        assert "class SimpleScreenPage" in code

    def test_fluent_pattern(self, simple_screen):
        """Test fluent interface pattern (placeholder)"""
        generator = SkeletonTestGenerator(
            Language.PYTHON,
            pattern=PageObjectPattern.FLUENT
        )

        # For now, it uses classic pattern
        code = generator.generate_page_object(simple_screen)
        assert "class SimpleScreenPage" in code


class TestSelfHealingSelectors:
    """Test self-healing selector generation"""

    def test_selector_priority_with_id(self):
        """Test that ID is prioritized"""
        generator = SkeletonTestGenerator(Language.PYTHON)

        element = UIElement(
            id="my_id",
            type="button",
            label="Test",
            xpath="//button",
            accessibility_id="my_acc_id",
            bounds={},
            visible=True,
            enabled=True
        )

        strategy = generator.generate_selector_strategy(element)

        assert strategy.primary.startswith("id=")
        assert strategy.stability_score == 1.0

    def test_selector_fallback_to_accessibility_id(self):
        """Test fallback to accessibility ID when no ID"""
        generator = SkeletonTestGenerator(Language.PYTHON)

        element = UIElement(
            id="",
            type="button",
            label="Test",
            xpath="//button",
            accessibility_id="my_acc_id",
            bounds={},
            visible=True,
            enabled=True
        )

        strategy = generator.generate_selector_strategy(element)

        assert "accessibility_id=" in strategy.primary
        assert strategy.stability_score == 0.8

    def test_selector_fallback_to_xpath(self):
        """Test fallback to xpath when no ID or accessibility ID"""
        generator = SkeletonTestGenerator(Language.PYTHON)

        element = UIElement(
            id="",
            type="button",
            label="Test",
            xpath="//button[@text='Test']",
            accessibility_id="",
            bounds={},
            visible=True,
            enabled=True
        )

        strategy = generator.generate_selector_strategy(element)

        assert "xpath=" in strategy.primary or "text=" in strategy.primary
        assert strategy.stability_score <= 0.8

    def test_multiple_fallback_strategies(self):
        """Test that multiple fallbacks are generated"""
        generator = SkeletonTestGenerator(Language.PYTHON)

        element = UIElement(
            id="my_id",
            type="button",
            label="Test Button",
            xpath="//button[@id='my_id']",
            accessibility_id="test_btn",
            bounds={},
            visible=True,
            enabled=True
        )

        strategy = generator.generate_selector_strategy(element)

        assert len(strategy.fallbacks) >= 2
        assert any("accessibility_id" in fb for fb in strategy.fallbacks)
        assert any("xpath" in fb for fb in strategy.fallbacks)


class TestMultiLanguageGeneration:
    """Test generation for all supported languages"""

    @pytest.fixture
    def test_screen(self):
        """Screen for testing all languages"""
        elements = [
            UIElement("test_btn", "button", "Test", "//button", "test", {}, True, True)
        ]
        return Screen("test", "TestScreen", elements, [], [])

    def test_all_languages_generate_page_objects(self, test_screen):
        """Test that all languages generate valid page objects"""
        for lang in Language:
            generator = SkeletonTestGenerator(lang)
            code = generator.generate_page_object(test_screen)

            assert code
            assert len(code) > 0
            assert "TestScreen" in code

    def test_all_languages_generate_test_scaffolds(self, test_screen):
        """Test that supported languages generate test scaffolds"""
        # Python and Java have scaffold implementations
        for lang in [Language.PYTHON, Language.JAVA]:
            generator = SkeletonTestGenerator(lang)
            code = generator.generate_test_scaffold(test_screen)

            assert code
            assert "TestScreen" in code or "test_" in code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
