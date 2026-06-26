"""
Training data generator for ML element classifier.

Creates labeled training data from recorded sessions using rule-based classification
or manual labeling interface.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from framework.model.app_model import ElementType

logger = logging.getLogger(__name__)


class TrainingDataGenerator:
    """
    Generate labeled training data for ML classifier.

    Strategies:
    1. Auto-labeling using rule-based heuristics
    2. Manual labeling via CLI
    3. Import from existing test code
    """

    def __init__(self):
        """Initialize generator."""
        self.labeled_data = []

    def auto_label_hierarchy_events(self, hierarchy_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Automatically label elements using rule-based heuristics.

        Args:
            hierarchy_events: Unlabeled hierarchy events

        Returns:
            Labeled hierarchy events
        """
        labeled_events = []

        for event in hierarchy_events:
            hierarchy_str = event.get("hierarchy", "{}")
            hierarchy = json.loads(hierarchy_str) if isinstance(hierarchy_str, str) else hierarchy_str

            # Label all elements in hierarchy
            labeled_hierarchy = self._label_hierarchy_recursive(hierarchy)

            # Update event with labeled hierarchy
            labeled_event = event.copy()
            labeled_event["hierarchy"] = json.dumps(labeled_hierarchy)
            labeled_events.append(labeled_event)

        logger.info(f"Auto-labeled {len(labeled_events)} hierarchy events")

        return labeled_events

    def _label_hierarchy_recursive(self, node: Dict[str, Any], depth: int = 0) -> Dict[str, Any]:
        """Recursively label elements in hierarchy tree."""
        labeled_node = node.copy()

        # Infer element type using rule-based heuristics
        element_type = self._infer_element_type(node)
        labeled_node["element_type"] = element_type.value

        # Process children
        if "children" in node:
            labeled_node["children"] = [self._label_hierarchy_recursive(child, depth + 1) for child in node["children"]]

        return labeled_node

    def _infer_element_type(self, element: Dict[str, Any]) -> ElementType:
        """
        Infer element type using rule-based heuristics.

        This is a simplified version - the ML model will learn to do this better.
        """
        class_name = element.get("class", "").lower()
        text = element.get("text", "")
        content_desc = element.get("content_desc", "") or element.get("label", "")
        clickable = element.get("clickable", False)
        checkable = element.get("checkable", False)
        password = element.get("password", False)

        # Button detection - improved with content_desc
        if "button" in class_name or "btn" in class_name.lower():
            return ElementType.BUTTON
        if clickable and ("button" in content_desc.lower() or "btn" in content_desc.lower()):
            return ElementType.BUTTON

        # Input field detection
        if "edit" in class_name or "textfield" in class_name or "input" in class_name:
            if password:
                return ElementType.INPUT  # Password input
            return ElementType.INPUT

        # Checkbox detection - improved with checkable attribute
        if "checkbox" in class_name or "check" in class_name or checkable:
            return ElementType.CHECKBOX

        # Radio button detection
        if "radio" in class_name or "radio" in content_desc.lower():
            return ElementType.RADIO

        # Switch detection
        if "switch" in class_name or "toggle" in class_name:
            return ElementType.SWITCH

        # List detection
        if "recycler" in class_name or "listview" in class_name or "collection" in class_name:
            return ElementType.LIST

        # Image detection
        if "image" in class_name or "icon" in class_name:
            return ElementType.IMAGE

        # Text detection
        if text and len(text) > 3 and not clickable:
            if "text" in class_name:
                return ElementType.TEXT

        # WebView detection
        if "webview" in class_name:
            return ElementType.WEBVIEW

        # Clickable without specific type = button
        if clickable and not text:
            return ElementType.BUTTON

        # Text with clickable = button
        if clickable and text:
            return ElementType.BUTTON

        # Default
        return ElementType.GENERIC

    def generate_synthetic_dataset(
            self, num_samples: int = 1000, output_path: Path = Path("training_data/synthetic_elements.json")
    ):
        """
        Generate synthetic training dataset with labeled examples.

        Args:
            num_samples: Number of samples to generate
            output_path: Output file path
        """
        import random

        synthetic_data = []

        # Define templates for each element type
        templates = {
            ElementType.BUTTON: [
                {"class": "android.widget.Button", "clickable": True, "text": "Submit"},
                {"class": "android.widget.ImageButton", "clickable": True, "content_desc": "Back"},
                {"class": "androidx.compose.material.Button", "clickable": True, "text": "Login"},
            ],
            ElementType.INPUT: [
                {"class": "android.widget.EditText", "focusable": True, "text": "", "password": False},
                {"class": "android.widget.EditText", "focusable": True, "text": "", "password": True},
                {"class": "androidx.compose.foundation.text.TextField", "focusable": True},
            ],
            ElementType.TEXT: [
                {"class": "android.widget.TextView", "text": "Welcome to the app", "clickable": False},
                {"class": "android.widget.TextView", "text": "Description text here", "clickable": False},
            ],
            ElementType.CHECKBOX: [
                {"class": "android.widget.CheckBox", "checkable": True, "clickable": True},
                {"class": "androidx.compose.material.Checkbox", "checkable": True},
            ],
            ElementType.SWITCH: [
                {"class": "android.widget.Switch", "checkable": True, "clickable": True},
                {"class": "androidx.compose.material.Switch", "checkable": True},
            ],
            ElementType.IMAGE: [
                {"class": "android.widget.ImageView", "clickable": False},
                {"class": "android.widget.ImageView", "content_desc": "Profile picture"},
            ],
            ElementType.LIST: [
                {"class": "androidx.recyclerview.widget.RecyclerView", "scrollable": True},
                {"class": "android.widget.ListView", "scrollable": True},
            ],
        }

        # Generate samples
        for _ in range(num_samples):
            element_type = random.choice(list(templates.keys()))
            template = random.choice(templates[element_type])

            # Add random variations
            element = template.copy()
            element["element_type"] = element_type.value
            element["bounds"] = {"width": random.randint(50, 800), "height": random.randint(30, 200)}
            element["depth"] = random.randint(0, 10)
            element["children_count"] = random.randint(0, 5)

            synthetic_data.append(element)

        # Save to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(synthetic_data, f, indent=2)

        logger.info(f"Generated {num_samples} synthetic training samples at {output_path}")

        return output_path

    def generate_from_app_model(
            self,
            app_model: Dict[str, Any],
            output_path: Optional[Path] = None
    ) -> Path:
        """
        Generate training data from app model.

        Args:
            app_model: Application model with screens and elements
            output_path: Output file path

        Returns:
            Path to generated training data
        """
        path = output_path or Path("ml_models/app_training_data.json")
        training_data = []

        # Extract elements from app model
        screens = app_model.get("screens", [])
        for screen in screens:
            elements = screen.get("elements", [])
            for element in elements:
                # Add element type label based on heuristics
                element_type = self._infer_element_type(element)
                element["element_type"] = element_type.value
                training_data.append(element)

        # Save to file
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(training_data, f, indent=2)

        logger.info(f"Generated {len(training_data)} samples from app model at {path}")
        return path

    def save_labeled_data(self, labeled_events: List[Dict[str, Any]], output_path: Path):
        """Save labeled training data to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(labeled_events, f, indent=2)

        logger.info(f"Saved {len(labeled_events)} labeled events to {output_path}")

    def prepare_for_training(self, labeled_events_path: Path) -> Dict[str, Any]:
        """
        Load and prepare labeled data for training.

        Args:
            labeled_events_path: Path to labeled events JSON

        Returns:
            Training data dict with events
        """
        with open(labeled_events_path, "r") as f:
            labeled_events = json.load(f)

        return {"events": labeled_events, "total_samples": len(labeled_events)}


def create_demo_training_dataset():
    """Create a demo training dataset for testing."""
    generator = TrainingDataGenerator()

    # Generate synthetic data
    output_path = Path("training_data/demo_elements.json")
    generator.generate_synthetic_dataset(num_samples=500, output_path=output_path)

    return output_path
