"""
Unit tests for the core UI data models (Language, UIElement, Screen).

The legacy CoreEngine multi-language generator and UIElement.to_selector were
removed (superseded by framework/codegen); only the data-model tests remain.
"""

from framework.core.engine import UIElement, Screen


class TestUIElement:
    """Test UIElement data model"""

    def test_create_ui_element(self):
        elem = UIElement(
            id="login_button",
            type="button",
            label="Login",
            xpath="//android.widget.Button[@text='Login']",
            accessibility_id="login_btn",
            bounds={"x": 100, "y": 200, "width": 50, "height": 30},
            visible=True,
            enabled=True,
        )

        assert elem.id == "login_button"
        assert elem.type == "button"
        assert elem.visible
        assert elem.enabled


class TestScreen:
    """Test Screen data model"""

    def test_create_screen(self):
        elements = [
            UIElement("id1", "button", "Button 1", None, None, {}, True, True),
            UIElement("id2", "textfield", "Text", None, None, {}, True, True),
        ]

        screen = Screen(id="screen1", name="LoginScreen", elements=elements, transitions=[], api_calls=[])

        assert screen.id == "screen1"
        assert len(screen.elements) == 2

    def test_find_interactive_elements(self):
        elements = [
            UIElement("btn1", "button", "Button", None, None, {}, True, True),
            UIElement("txt1", "textfield", "Text", None, None, {}, True, True),
            UIElement("lbl1", "label", "Label", None, None, {}, True, False),  # Not enabled
        ]

        screen = Screen("s1", "Test", elements, [], [])
        interactive = screen.find_interactive_elements()

        assert len(interactive) == 2
        assert all(e.enabled for e in interactive)
