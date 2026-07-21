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
        """Infer an element's type with the crawler's canonical rule heuristic.

        This used to carry its own copy of the class -> type rules (a second
        implementation that even mislabelled RadioButton as a button, since it
        checked "button" before "radio"). It now delegates to the single source of
        truth, ``framework.crawler.classify._heuristic`` — which is behaviour-aware
        (scrollable/focusable) and correct on the overlapping class names — adapting
        the event dict to a CrawlElement. The generator-specific ``checkable ->
        checkbox`` mapping (the heuristic keys checkboxes off the class name) is kept
        for otherwise-unclassified elements.
        """
        from framework.crawler.app_crawler import CrawlElement
        from framework.crawler.classify import _heuristic

        ce = CrawlElement(
            resource_id=element.get("resource-id", "") or element.get("resource_id", "") or "",
            text=element.get("text", "") or "",
            content_desc=element.get("content_desc", "") or element.get("label", "") or "",
            class_name=element.get("class", "") or "",
            clickable=bool(element.get("clickable")),
            bounds=(0, 0, 0, 0),
            checkable=bool(element.get("checkable")),
            focusable=bool(element.get("focusable")),
            password=bool(element.get("password")),
        )
        try:
            element_type = ElementType(_heuristic(ce))
        except ValueError:  # a heuristic label with no ElementType member
            element_type = ElementType.GENERIC
        if element_type is ElementType.GENERIC and ce.checkable:
            element_type = ElementType.CHECKBOX  # a bare checkable control -> checkbox
        return element_type

    def generate_synthetic_dataset(
        self,
        num_samples: int = 1000,
        output_path: Path = Path("training_data/synthetic_elements.json"),
        hard_fraction: float = 0.45,
    ):
        """
        Generate a synthetic training dataset with labeled examples.

        Args:
            num_samples: Number of samples to generate.
            output_path: Output file path.
            hard_fraction: Share drawn from the *hard* templates — ambiguous cases
                whose framework class does NOT name the type, so the label can only
                be recovered from other features (clickable, scrollable, checkable,
                size, text shape). Easy, class-named cases teach the model nothing
                the heuristic doesn't already know; the hard cases are where ML has
                to earn its keep, on both Android and iOS.

        Returns:
            The output path.
        """
        import random

        synthetic_data = []

        # HARD templates: the class is a generic container (Android View/ViewGroup/
        # FrameLayout & Compose's single AndroidComposeView; iOS "Other"/plain
        # StaticText), so the type is decidable only from behaviour + geometry.
        hard_templates = {
            ElementType.BUTTON: [
                {"class": "android.view.View", "clickable": True, "text": "Continue"},
                {"class": "android.view.ViewGroup", "clickable": True, "content_desc": "Add to cart"},
                {"class": "android.widget.FrameLayout", "clickable": True, "content_desc": "Menu"},
                {"class": "androidx.compose.ui.platform.ComposeView", "clickable": True, "text": "Log in"},
                {"class": "XCUIElementTypeOther", "clickable": True, "text": "Confirm"},
                {"class": "XCUIElementTypeStaticText", "clickable": True, "text": "See all"},  # tappable label
            ],
            ElementType.LIST: [
                {"class": "android.view.ViewGroup", "scrollable": True, "children_count": 8},
                {"class": "androidx.compose.foundation.lazy.LazyColumn", "scrollable": True, "children_count": 12},
                {"class": "XCUIElementTypeOther", "scrollable": True, "children_count": 10},
            ],
            ElementType.SWITCH: [  # custom toggle: small, square-ish, checkable, no "switch" in class
                {"class": "android.view.View", "checkable": True, "clickable": True, "_wh": (52, 32)},
                {"class": "XCUIElementTypeOther", "checkable": True, "clickable": True, "_wh": (50, 30)},
            ],
            ElementType.INPUT: [  # focusable, empty, editable, generic class
                {"class": "android.view.View", "focusable": True, "clickable": True, "text": ""},
                {"class": "androidx.compose.foundation.text.BasicTextField", "focusable": True, "text": ""},
                {"class": "XCUIElementTypeOther", "focusable": True, "clickable": True, "text": ""},
            ],
            ElementType.TEXT: [  # generic, has text, NOT interactive
                {"class": "android.view.View", "text": "Total balance 1,204.55", "clickable": False},
                {"class": "XCUIElementTypeOther", "text": "Recent activity", "clickable": False},
            ],
            ElementType.IMAGE: [  # decorative: non-clickable, no text, square-ish, generic
                {"class": "android.view.View", "clickable": False, "_wh": (96, 96)},
                {"class": "XCUIElementTypeOther", "clickable": False, "content_desc": "avatar", "_wh": (80, 80)},
            ],
        }

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

        # Generate samples, mixing in the hard (class-ambiguous) cases.
        for _ in range(num_samples):
            pool = hard_templates if random.random() < hard_fraction else templates
            element_type = random.choice(list(pool.keys()))
            template = random.choice(pool[element_type])

            # Add random variations
            element = template.copy()
            element["element_type"] = element_type.value
            # A template may pin a size (a small square toggle, a decorative image);
            # otherwise vary it so the model doesn't overfit fixed geometry.
            wh = element.pop("_wh", None)
            if wh is not None:
                element["bounds"] = {"width": wh[0], "height": wh[1]}
            else:
                element["bounds"] = {"width": random.randint(50, 800), "height": random.randint(30, 200)}
            element["depth"] = random.randint(0, 10)
            element.setdefault("children_count", random.randint(0, 5))

            synthetic_data.append(element)

        # Save to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(synthetic_data, f, indent=2)

        logger.info(f"Generated {num_samples} synthetic training samples at {output_path}")

        return output_path

    def generate_from_app_model(self, app_model: Dict[str, Any], output_path: Optional[Path] = None) -> Path:
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
