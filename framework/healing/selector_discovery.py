"""
Selector discovery

Discovers alternative selectors for elements when original selector fails.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional


class SelectorStrategy(Enum):
    """Strategy for selector generation"""
    ID = "id"
    XPATH = "xpath"
    CSS = "css"
    CLASS_NAME = "class_name"
    ACCESSIBILITY_ID = "accessibility_id"
    TEXT = "text"
    PARTIAL_TEXT = "partial_text"


@dataclass
class AlternativeSelector:
    """Represents an alternative selector"""
    strategy: SelectorStrategy
    value: str
    confidence: float  # 0.0 - 1.0
    element_attributes: Dict[str, str]

    @property
    def selector_tuple(self) -> tuple:
        """Return as (type, value) tuple"""
        return (self.strategy.value, self.value)

    def __repr__(self):
        return f"AlternativeSelector({self.strategy.value}, '{self.value}', confidence={self.confidence:.2f})"


class SelectorDiscovery:
    """
    Discovers alternative selectors from page source
    """

    def __init__(self):
        self.alternatives: List[AlternativeSelector] = []

    def discover_from_page_source(
            self,
            page_source_path: Path,
            original_selector: tuple
    ) -> List[AlternativeSelector]:
        """
        Discover alternative selectors from page source XML

        Args:
            page_source_path: Path to page source XML file
            original_selector: Original (type, value) selector that failed

        Returns:
            List of alternative selectors
        """
        self.alternatives = []

        try:
            tree = ET.parse(page_source_path)
            root = tree.getroot()

            # Find all interactive elements
            elements = self._find_interactive_elements(root)

            # Generate selectors for each element
            for elem in elements:
                selectors = self._generate_selectors_for_element(elem)
                self.alternatives.extend(selectors)

            # Sort by confidence
            self.alternatives.sort(key=lambda x: x.confidence, reverse=True)

        except (ET.ParseError, ValueError, TypeError) as e:
            print(f"Error parsing page source: {e}")

        return self.alternatives

    def _find_interactive_elements(self, root: ET.Element) -> List[ET.Element]:
        """Find all interactive/clickable elements"""
        interactive = []

        for elem in root.iter():
            # Check if element is interactive
            if self._is_interactive(elem):
                interactive.append(elem)

        return interactive

    def _is_interactive(self, elem: ET.Element) -> bool:
        """Check if element is interactive"""
        # Check class name
        class_name = elem.get('class', '')
        interactive_classes = [
            'Button', 'EditText', 'TextView', 'ImageButton',
            'UIButton', 'UITextField', 'UILabel', 'UITextView'
        ]

        if any(cls in class_name for cls in interactive_classes):
            return True

        # Check if clickable
        if elem.get('clickable') == 'true':
            return True

        # Check if has text
        text = elem.get('text', '')
        content_desc = elem.get('content-desc', '')
        if text or content_desc:
            return True

        return False

    def _generate_selectors_for_element(self, elem: ET.Element) -> List[AlternativeSelector]:
        """Generate all possible selectors for an element"""
        selectors = []
        attributes = elem.attrib

        # ID selector (highest confidence)
        resource_id = attributes.get('resource-id', '')
        if resource_id:
            selectors.append(AlternativeSelector(
                strategy=SelectorStrategy.ID,
                value=resource_id,
                confidence=0.95,
                element_attributes=dict(attributes)
            ))

        # Accessibility ID (iOS)
        accessibility_id = attributes.get('name', '') or attributes.get('label', '')
        if accessibility_id:
            selectors.append(AlternativeSelector(
                strategy=SelectorStrategy.ACCESSIBILITY_ID,
                value=accessibility_id,
                confidence=0.90,
                element_attributes=dict(attributes)
            ))

        # Text selector
        text = attributes.get('text', '')
        if text:
            selectors.append(AlternativeSelector(
                strategy=SelectorStrategy.TEXT,
                value=text,
                confidence=0.70,
                element_attributes=dict(attributes)
            ))

            # Partial text (more flexible)
            if len(text) > 3:
                selectors.append(AlternativeSelector(
                    strategy=SelectorStrategy.PARTIAL_TEXT,
                    value=text,
                    confidence=0.65,
                    element_attributes=dict(attributes)
                ))

        # Content description (Android)
        content_desc = attributes.get('content-desc', '')
        if content_desc:
            selectors.append(AlternativeSelector(
                strategy=SelectorStrategy.TEXT,
                value=content_desc,
                confidence=0.75,
                element_attributes=dict(attributes)
            ))

        # XPath selector (lower confidence, but works)
        xpath = self._generate_xpath(elem)
        selectors.append(AlternativeSelector(
            strategy=SelectorStrategy.XPATH,
            value=xpath,
            confidence=0.50,
            element_attributes=dict(attributes)
        ))

        # Class-based XPath (more stable)
        class_name = attributes.get('class', '')
        if class_name:
            class_xpath = f"//{class_name}[@text='{text}']" if text else f"//{class_name}"
            selectors.append(AlternativeSelector(
                strategy=SelectorStrategy.XPATH,
                value=class_xpath,
                confidence=0.60,
                element_attributes=dict(attributes)
            ))

        return selectors

    def _generate_xpath(self, elem: ET.Element) -> str:
        """Generate XPath for element"""
        # Build path from root
        path_parts = []
        current = elem

        while current is not None:
            # Get element position among siblings
            parent = self._get_parent(current)
            if parent is not None:
                siblings = [e for e in parent if e.tag == current.tag]
                if len(siblings) > 1:
                    index = siblings.index(current) + 1
                    path_parts.insert(0, f"{current.tag}[{index}]")
                else:
                    path_parts.insert(0, current.tag)
            else:
                path_parts.insert(0, current.tag)

            current = parent

        return '//' + '/'.join(path_parts)

    def _get_parent(self, elem: ET.Element) -> Optional[ET.Element]:
        """Get parent of element (not directly supported in ElementTree)"""
        # This is a simplified version
        # In real implementation, maintain parent map
        return None

    def filter_by_attributes(
            self, required_attributes: Dict[str, str]
    ) -> List[AlternativeSelector]:
        """
        Filter alternatives by matching attributes

        Args:
            required_attributes: Dict of attribute names and values that must match

        Returns:
            Filtered list of alternatives
        """
        filtered = []

        return filtered

    def boost_confidence_by_context(
            self,
            screen_name: Optional[str] = None,
            nearby_text: Optional[List[str]] = None
    ):
        """
        Adjust confidence scores based on context

        Args:
            screen_name: Name of screen/activity
            nearby_text: List of text visible near the element
        """
        for selector in self.alternatives:
            # Boost if screen name matches
            if screen_name:
                class_name = selector.element_attributes.get('class', '')
                if screen_name.lower() in class_name.lower():
                    selector.confidence = min(1.0, selector.confidence + 0.10)

            # Boost if nearby text matches
            if nearby_text:
                elem_text = selector.element_attributes.get('text', '')
                for text in nearby_text:
                    if text.lower() in elem_text.lower():
                        selector.confidence = min(1.0, selector.confidence + 0.05)

    def generate_report(self) -> str:
        """Generate report of discovered alternatives"""
        if not self.alternatives:
            return "No alternative selectors found."

        report = "ALTERNATIVE SELECTORS\n"
        report += "=" * 80 + "\n\n"
        report += f"Found {len(self.alternatives)} alternative selector(s):\n\n"

        for i, alt in enumerate(self.alternatives[:10], 1):  # Top 10
            report += f"{i}. {alt.strategy.value}: '{alt.value}'\n"
            report += f"   Confidence: {alt.confidence:.2f}\n"
            report += f"   Attributes: {list(alt.element_attributes.keys())}\n"
            report += "\n"

        if len(self.alternatives) > 10:
            report += f"... and {len(self.alternatives) - 10} more\n"

        report += "=" * 80 + "\n"

        return report
