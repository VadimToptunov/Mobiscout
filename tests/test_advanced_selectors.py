"""
Tests for Advanced Selector Engine
"""

import pytest

from framework.selectors.advanced_selector import (
    AdvancedSelector,
    AdvancedSelectorEngine,
    SelectorBuilder,
    SelectorType,
    FilterOperator,
    SelectorFilter,
    by_id,
    by_text,
    by_class,
    contains_text,
)


@pytest.fixture
def sample_elements():
    """Create sample element hierarchy for testing"""
    return [
        {
            "id": "root",
            "parent_id": None,
            "class": "LinearLayout",
            "resource_id": "root_layout",
            "enabled": True,
            "visible": True,
        },
        {
            "id": "title",
            "parent_id": "root",
            "class": "TextView",
            "text": "Login Screen",
            "enabled": True,
            "visible": True,
        },
        {
            "id": "username_input",
            "parent_id": "root",
            "class": "EditText",
            "resource_id": "username",
            "text": "",
            "hint": "Username",
            "enabled": True,
            "visible": True,
        },
        {
            "id": "password_input",
            "parent_id": "root",
            "class": "EditText",
            "resource_id": "password",
            "text": "",
            "hint": "Password",
            "enabled": True,
            "visible": True,
        },
        {
            "id": "login_button",
            "parent_id": "root",
            "class": "Button",
            "resource_id": "login_btn",
            "text": "Login",
            "enabled": True,
            "visible": True,
        },
        {
            "id": "disabled_button",
            "parent_id": "root",
            "class": "Button",
            "resource_id": "disabled_btn",
            "text": "Disabled",
            "enabled": False,
            "visible": True,
        },
    ]


class TestSelectorFilter:
    """Test SelectorFilter functionality"""

    def test_equals_filter(self):
        """Test equals operator"""
        filter_obj = SelectorFilter("text", FilterOperator.EQUALS, "Login")
        assert filter_obj.matches({"text": "Login"}) is True
        assert filter_obj.matches({"text": "Logout"}) is False

    def test_contains_filter(self):
        """Test contains operator"""
        filter_obj = SelectorFilter("text", FilterOperator.CONTAINS, "Log")
        assert filter_obj.matches({"text": "Login"}) is True
        assert filter_obj.matches({"text": "Logout"}) is True
        assert filter_obj.matches({"text": "Submit"}) is False

    def test_starts_with_filter(self):
        """Test starts_with operator"""
        filter_obj = SelectorFilter("text", FilterOperator.STARTS_WITH, "Log")
        assert filter_obj.matches({"text": "Login"}) is True
        assert filter_obj.matches({"text": "Logout"}) is True
        assert filter_obj.matches({"text": "Blog"}) is False

    def test_has_attribute_filter(self):
        """Test has_attribute operator"""
        filter_obj = SelectorFilter("enabled", FilterOperator.HAS_ATTRIBUTE)
        assert filter_obj.matches({"enabled": True}) is True
        assert filter_obj.matches({"enabled": False}) is True
        assert filter_obj.matches({"text": "Test"}) is False

    def test_greater_than_filter(self):
        """Test greater_than operator"""
        filter_obj = SelectorFilter("width", FilterOperator.GREATER_THAN, 100)
        assert filter_obj.matches({"width": 150}) is True
        assert filter_obj.matches({"width": 50}) is False


class TestAdvancedSelector:
    """Test AdvancedSelector functionality"""

    def test_simple_id_selector(self, sample_elements):
        """Test simple ID selector"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = by_id("login_btn")
        results = engine.find(selector)

        assert len(results) == 1
        assert results[0]["id"] == "login_button"

    def test_simple_text_selector(self, sample_elements):
        """Test simple text selector"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = by_text("Login")
        results = engine.find(selector)

        assert len(results) == 1
        assert results[0]["text"] == "Login"

    def test_fuzzy_text_selector(self, sample_elements):
        """Test fuzzy text matching"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = by_text("log", fuzzy=True)
        results = engine.find(selector)

        # Should match "Login Screen" and "Login"
        assert len(results) == 2

    def test_class_selector(self, sample_elements):
        """Test class selector"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = by_class("Button")
        results = engine.find(selector)

        # Should find 2 buttons (enabled and disabled)
        assert len(results) == 2

    def test_contains_text_selector(self, sample_elements):
        """Test partial text matching"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = contains_text("Login")
        results = engine.find(selector)

        # Should match "Login Screen" and "Login"
        assert len(results) == 2

    def test_selector_with_filters(self, sample_elements):
        """Test selector with attribute filters"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = AdvancedSelector(
            type=SelectorType.CLASS,
            value="Button",
            filters=[SelectorFilter("enabled", FilterOperator.EQUALS, True)],
        )
        results = engine.find(selector)

        # Should only find enabled button
        assert len(results) == 1
        assert results[0]["id"] == "login_button"

    def test_index_selector(self, sample_elements):
        """Test index selection"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = AdvancedSelector(type=SelectorType.CLASS, value="EditText", index=1)
        results = engine.find(selector)

        # Should select second EditText (password)
        assert len(results) == 1
        assert results[0]["id"] == "password_input"

    def test_to_appium_android(self):
        """Test conversion to Appium format for Android"""
        selector = by_id("login_btn")
        appium_selector = selector.to_appium("android")

        assert appium_selector == {"id": "login_btn"}

    def test_to_appium_text(self):
        """Test text selector conversion to XPath"""
        selector = by_text("Login")
        appium_selector = selector.to_appium("android")

        assert "xpath" in appium_selector
        assert '@text="Login"' in appium_selector["xpath"]


class TestRelationshipSelectors:
    """Test relationship-based selectors"""

    def test_parent_relationship(self, sample_elements):
        """Test finding element by parent"""
        engine = AdvancedSelectorEngine(sample_elements)

        # Find button that has root_layout as parent
        selector = AdvancedSelector(
            type=SelectorType.CLASS,
            value="Button",
            relationship=SelectorType.PARENT,
            relationship_target=AdvancedSelector(type=SelectorType.ID, value="root_layout"),
        )

        results = engine.find(selector)
        assert len(results) == 2  # Both buttons have root as parent

    def test_sibling_relationship(self, sample_elements):
        """Test finding element by sibling"""
        engine = AdvancedSelectorEngine(sample_elements)

        # Find EditText that has Button as sibling
        selector = AdvancedSelector(
            type=SelectorType.CLASS,
            value="EditText",
            relationship=SelectorType.SIBLING,
            relationship_target=AdvancedSelector(type=SelectorType.CLASS, value="Button"),
        )

        results = engine.find(selector)
        assert len(results) == 2  # Both EditTexts have Button siblings

    def test_child_relationship(self, sample_elements):
        """Test finding element by child"""
        engine = AdvancedSelectorEngine(sample_elements)

        # Find layout that has EditText as child
        selector = AdvancedSelector(
            type=SelectorType.CLASS,
            value="LinearLayout",
            relationship=SelectorType.CHILD,
            relationship_target=AdvancedSelector(type=SelectorType.CLASS, value="EditText"),
        )

        results = engine.find(selector)
        assert len(results) == 1  # Root has EditText children


class TestFluentSelectorBuilder:
    """Test fluent builder API"""

    def test_build_by_id(self, sample_elements):
        """Test building ID selector with fluent API"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = SelectorBuilder().by_id("login_btn").build()
        results = engine.find(selector)

        assert len(results) == 1
        assert results[0]["id"] == "login_button"

    def test_build_with_filters(self, sample_elements):
        """Test building selector with filters"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = (
            SelectorBuilder()
            .by_class("Button")
            .with_attribute("enabled", FilterOperator.EQUALS, True)
            .that_is_visible()
            .build()
        )
        results = engine.find(selector)

        assert len(results) == 1
        assert results[0]["enabled"] is True

    def test_build_with_index(self, sample_elements):
        """Test building selector with index"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = SelectorBuilder().by_class("EditText").at_index(0).build()
        results = engine.find(selector)

        assert len(results) == 1
        assert results[0]["id"] == "username_input"

    def test_build_fuzzy_text(self, sample_elements):
        """Test building fuzzy text selector"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = SelectorBuilder().by_text("log", fuzzy=True).build()
        results = engine.find(selector)

        assert len(results) >= 1

    def test_build_chained_filters(self, sample_elements):
        """Test building selector with multiple chained filters"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = (
            SelectorBuilder()
            .by_class("Button")
            .that_is_enabled()
            .with_attribute("text", FilterOperator.CONTAINS, "Login")
            .build()
        )
        results = engine.find(selector)

        assert len(results) == 1
        assert results[0]["text"] == "Login"


class TestComplexQueries:
    """Test complex selector queries"""

    def test_find_enabled_input_next_to_button(self, sample_elements):
        """Test finding enabled input field next to a button"""
        engine = AdvancedSelectorEngine(sample_elements)

        # Find enabled EditText with Button sibling
        selector = (
            SelectorBuilder()
            .by_class("EditText")
            .that_is_enabled()
            .with_sibling(AdvancedSelector(type=SelectorType.CLASS, value="Button"))
            .build()
        )

        results = engine.find(selector)
        assert len(results) == 2  # username and password inputs

    def test_fuzzy_class_matching(self, sample_elements):
        """Test fuzzy class name matching"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = by_class("edit", fuzzy=True)
        results = engine.find(selector)

        # Should match EditText
        assert len(results) == 2

    def test_multiple_filters(self, sample_elements):
        """Test element with multiple attribute filters"""
        engine = AdvancedSelectorEngine(sample_elements)
        selector = AdvancedSelector(
            type=SelectorType.CLASS,
            value="Button",
            filters=[
                SelectorFilter("enabled", FilterOperator.EQUALS, True),
                SelectorFilter("visible", FilterOperator.EQUALS, True),
                SelectorFilter("text", FilterOperator.CONTAINS, "Login"),
            ],
        )
        results = engine.find(selector)

        assert len(results) == 1
        assert results[0]["text"] == "Login"


def test_real_world_example(sample_elements):
    """Test a real-world scenario: finding login button"""
    engine = AdvancedSelectorEngine(sample_elements)

    # Find button with text "Login", that is enabled and visible
    selector = (
        SelectorBuilder()
        .contains_text("Login")
        .with_attribute("class", FilterOperator.EQUALS, "Button")
        .that_is_enabled()
        .that_is_visible()
        .build()
    )

    results = engine.find(selector)

    assert len(results) == 1
    assert results[0]["id"] == "login_button"
    assert results[0]["enabled"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
