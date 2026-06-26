"""
Advanced Selector Engine

Provides advanced selector capabilities:
- Relative selectors (parent, sibling, child relationships)
- Chained filters
- Smart fuzzy matching
- Custom selector strategies
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any


def escape_xpath_value(value: str) -> str:
    """
    Escape a string value for safe use in XPath expressions.

    Handles quotes by using concat() when necessary.
    """
    if '"' not in value:
        return f'"{value}"'
    elif "'" not in value:
        return f"'{value}'"
    else:
        # Value contains both quotes - use concat()
        parts = value.split('"')
        escaped_parts = [f'"{part}"' for part in parts]
        return "concat(" + ", '\"', ".join(escaped_parts) + ")"


class SelectorType(Enum):
    """Advanced selector types"""

    ID = "id"
    XPATH = "xpath"
    ACCESSIBILITY = "accessibility_id"
    CLASS = "class_name"
    TEXT = "text"
    CONTAINS_TEXT = "contains_text"
    ATTRIBUTE = "attribute"
    INDEX = "index"
    PARENT = "parent"
    CHILD = "child"
    SIBLING = "sibling"
    ANCESTOR = "ancestor"
    DESCENDANT = "descendant"


class FilterOperator(Enum):
    """Filter operators for chaining"""

    EQUALS = "=="
    NOT_EQUALS = "!="
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"  # regex
    GREATER_THAN = ">"
    LESS_THAN = "<"
    HAS_ATTRIBUTE = "has_attr"


@dataclass
class SelectorFilter:
    """A filter to apply to selector results"""

    attribute: str
    operator: FilterOperator
    value: Optional[Any] = None

    def matches(self, element: Dict[str, Any]) -> bool:
        """Check if element matches this filter"""
        attr_value = element.get(self.attribute)

        if self.operator == FilterOperator.HAS_ATTRIBUTE:
            return attr_value is not None

        if attr_value is None:
            return False

        if self.operator == FilterOperator.EQUALS:
            return attr_value == self.value

        if self.operator == FilterOperator.NOT_EQUALS:
            return attr_value != self.value

        if self.operator == FilterOperator.CONTAINS:
            return str(self.value) in str(attr_value)

        if self.operator == FilterOperator.STARTS_WITH:
            return str(attr_value).startswith(str(self.value))

        if self.operator == FilterOperator.ENDS_WITH:
            return str(attr_value).endswith(str(self.value))

        if self.operator == FilterOperator.MATCHES:
            import re

            return bool(re.search(str(self.value), str(attr_value)))

        if self.operator == FilterOperator.GREATER_THAN:
            try:
                return float(attr_value) > float(self.value)
            except (ValueError, TypeError):
                return False

        if self.operator == FilterOperator.LESS_THAN:
            try:
                return float(attr_value) < float(self.value)
            except (ValueError, TypeError):
                return False

        return False


@dataclass
class AdvancedSelector:
    """
    Advanced selector with relationships and filters

    Examples:
        # Simple selector
        AdvancedSelector(type=SelectorType.ID, value="login_button")

        # With filters
        AdvancedSelector(
            type=SelectorType.CLASS,
            value="Button",
            filters=[
                SelectorFilter("enabled", FilterOperator.EQUALS, True),
                SelectorFilter("text", FilterOperator.CONTAINS, "Login")
            ]
        )

        # Relative selector
        AdvancedSelector(
            type=SelectorType.TEXT,
            value="Username",
            relationship=SelectorType.SIBLING,
            relationship_target=AdvancedSelector(type=SelectorType.CLASS, value="EditText")
        )
    """

    type: SelectorType
    value: str
    filters: List[SelectorFilter] = None
    relationship: Optional[SelectorType] = None
    relationship_target: Optional["AdvancedSelector"] = None
    index: Optional[int] = None  # If multiple matches, pick this index
    fuzzy: bool = False  # Enable fuzzy matching

    def __post_init__(self):
        if self.filters is None:
            self.filters = []

    def to_appium(self, platform: str = "android") -> Dict[str, str]:
        """Convert to Appium selector format"""
        if self.type == SelectorType.ID:
            return {"id": self.value}

        if self.type == SelectorType.XPATH:
            return {"xpath": self.value}

        if self.type == SelectorType.ACCESSIBILITY:
            return {"accessibility id": self.value}

        if self.type == SelectorType.CLASS:
            return {"class name": self.value}

        if self.type == SelectorType.TEXT:
            # Escape value to prevent XPath injection
            escaped_value = escape_xpath_value(self.value)
            if platform == "android":
                return {"xpath": f'//*[@text={escaped_value}]'}
            else:  # iOS
                return {"xpath": f'//*[@label={escaped_value} or @value={escaped_value}]'}

        if self.type == SelectorType.CONTAINS_TEXT:
            # Escape value to prevent XPath injection
            escaped_value = escape_xpath_value(self.value)
            if platform == "android":
                return {"xpath": f'//*[contains(@text, {escaped_value})]'}
            else:  # iOS
                return {"xpath": f'//*[contains(@label, {escaped_value}) or contains(@value, {escaped_value})]'}

        return {}

    def matches(self, element: Dict[str, Any]) -> bool:
        """Check if element matches all filters"""
        return all(f.matches(element) for f in self.filters)


class AdvancedSelectorEngine:
    """
    Engine for executing advanced selectors
    """

    def __init__(self, elements: List[Dict[str, Any]]):
        """
        Initialize with element hierarchy

        Args:
            elements: List of element dictionaries with attributes
        """
        # Deep copy elements to avoid modifying original data
        import copy
        self.elements = copy.deepcopy(elements)
        self._build_relationships()

    def _build_relationships(self):
        """Build parent-child-sibling relationships"""
        # Build element tree for relationship queries
        self.element_map = {el.get("id", i): el for i, el in enumerate(self.elements)}

        for element in self.elements:
            element["_children"] = []
            element["_siblings"] = []

        # Build parent-child relationships
        for element in self.elements:
            parent_id = element.get("parent_id")
            if parent_id and parent_id in self.element_map:
                parent = self.element_map[parent_id]
                parent["_children"].append(element)

        # Build sibling relationships
        for element in self.elements:
            parent_id = element.get("parent_id")
            if parent_id and parent_id in self.element_map:
                parent = self.element_map[parent_id]
                siblings = [child for child in parent["_children"] if child != element]
                element["_siblings"] = siblings

    def find(self, selector: AdvancedSelector) -> List[Dict[str, Any]]:
        """
        Find elements matching the selector

        Returns list of matching elements
        """
        # Start with all elements
        candidates = self.elements.copy()

        # Apply base selector
        candidates = self._apply_base_selector(candidates, selector)

        # Apply filters
        candidates = [el for el in candidates if selector.matches(el)]

        # Apply relationship if specified
        if selector.relationship and selector.relationship_target:
            candidates = self._apply_relationship(candidates, selector)

        # Apply index if specified
        if selector.index is not None and len(candidates) > selector.index:
            candidates = [candidates[selector.index]]

        return candidates

    def _apply_base_selector(
            self, candidates: List[Dict[str, Any]], selector: AdvancedSelector
    ) -> List[Dict[str, Any]]:
        """Apply the base selector type"""
        results = []

        for element in candidates:
            if self._matches_base(element, selector):
                results.append(element)

        return results

    def _matches_base(self, element: Dict[str, Any], selector: AdvancedSelector) -> bool:
        """Check if element matches base selector"""
        if selector.type == SelectorType.ID:
            return element.get("resource_id") == selector.value or element.get("id") == selector.value

        if selector.type == SelectorType.CLASS:
            class_name = element.get("class") or element.get("type")
            if selector.fuzzy:
                if class_name is None:
                    return False
                return selector.value.lower() in str(class_name).lower()
            return class_name == selector.value

        if selector.type == SelectorType.TEXT:
            text = element.get("text") or element.get("label")
            if selector.fuzzy:
                if text is None:
                    return False
                return selector.value.lower() in str(text).lower()
            return text == selector.value

        if selector.type == SelectorType.CONTAINS_TEXT:
            text = element.get("text") or element.get("label") or ""
            return selector.value in str(text)

        if selector.type == SelectorType.ACCESSIBILITY:
            return element.get("accessibility_id") == selector.value or element.get("name") == selector.value

        if selector.type == SelectorType.ATTRIBUTE:
            # Format: "attribute_name:attribute_value"
            if ":" in selector.value:
                attr_name, attr_value = selector.value.split(":", 1)
                return element.get(attr_name) == attr_value

        return False

    def _apply_relationship(
            self, candidates: List[Dict[str, Any]], selector: AdvancedSelector
    ) -> List[Dict[str, Any]]:
        """Apply relationship selector"""
        results = []

        for element in candidates:
            related_elements = self._get_related_elements(element, selector.relationship)

            # Check if any related element matches the target selector
            for related in related_elements:
                if self._matches_base(related, selector.relationship_target) and selector.relationship_target.matches(
                        related
                ):
                    results.append(element)
                    break

        return results

    def _get_related_elements(self, element: Dict[str, Any], relationship: SelectorType) -> List[Dict[str, Any]]:
        """Get related elements based on relationship type"""
        if relationship == SelectorType.PARENT:
            parent_id = element.get("parent_id")
            if parent_id and parent_id in self.element_map:
                return [self.element_map[parent_id]]
            return []

        if relationship == SelectorType.CHILD:
            return element.get("_children", [])

        if relationship == SelectorType.SIBLING:
            return element.get("_siblings", [])

        if relationship == SelectorType.ANCESTOR:
            ancestors = []
            current = element
            while True:
                parent_id = current.get("parent_id")
                if not parent_id or parent_id not in self.element_map:
                    break
                parent = self.element_map[parent_id]
                ancestors.append(parent)
                current = parent
            return ancestors

        if relationship == SelectorType.DESCENDANT:
            descendants = []

            def collect_descendants(el):
                for child in el.get("_children", []):
                    descendants.append(child)
                    collect_descendants(child)

            collect_descendants(element)
            return descendants

        return []


class SelectorBuilder:
    """Fluent builder for advanced selectors"""

    def __init__(self):
        self.selector = AdvancedSelector(type=SelectorType.XPATH, value="")

    def by_id(self, value: str) -> "SelectorBuilder":
        """Select by ID"""
        self.selector.type = SelectorType.ID
        self.selector.value = value
        return self

    def by_text(self, value: str, fuzzy: bool = False) -> "SelectorBuilder":
        """Select by text"""
        self.selector.type = SelectorType.TEXT
        self.selector.value = value
        self.selector.fuzzy = fuzzy
        return self

    def by_class(self, value: str, fuzzy: bool = False) -> "SelectorBuilder":
        """Select by class name"""
        self.selector.type = SelectorType.CLASS
        self.selector.value = value
        self.selector.fuzzy = fuzzy
        return self

    def contains_text(self, value: str) -> "SelectorBuilder":
        """Select by partial text match"""
        self.selector.type = SelectorType.CONTAINS_TEXT
        self.selector.value = value
        return self

    def with_attribute(self, name: str, operator: FilterOperator, value: Any) -> "SelectorBuilder":
        """Add attribute filter"""
        self.selector.filters.append(SelectorFilter(name, operator, value))
        return self

    def that_is_enabled(self) -> "SelectorBuilder":
        """Filter to enabled elements"""
        return self.with_attribute("enabled", FilterOperator.EQUALS, True)

    def that_is_visible(self) -> "SelectorBuilder":
        """Filter to visible elements"""
        return self.with_attribute("visible", FilterOperator.EQUALS, True)

    def with_parent(self, parent_selector: AdvancedSelector) -> "SelectorBuilder":
        """Add parent relationship"""
        self.selector.relationship = SelectorType.PARENT
        self.selector.relationship_target = parent_selector
        return self

    def with_sibling(self, sibling_selector: AdvancedSelector) -> "SelectorBuilder":
        """Add sibling relationship"""
        self.selector.relationship = SelectorType.SIBLING
        self.selector.relationship_target = sibling_selector
        return self

    def at_index(self, index: int) -> "SelectorBuilder":
        """Select specific index if multiple matches"""
        self.selector.index = index
        return self

    def build(self) -> AdvancedSelector:
        """Build the selector"""
        return self.selector


# Helper functions for quick selector creation
def by_id(value: str) -> AdvancedSelector:
    """Quick ID selector"""
    return AdvancedSelector(type=SelectorType.ID, value=value)


def by_text(value: str, fuzzy: bool = False) -> AdvancedSelector:
    """Quick text selector"""
    return AdvancedSelector(type=SelectorType.TEXT, value=value, fuzzy=fuzzy)


def by_class(value: str, fuzzy: bool = False) -> AdvancedSelector:
    """Quick class selector"""
    return AdvancedSelector(type=SelectorType.CLASS, value=value, fuzzy=fuzzy)


def contains_text(value: str) -> AdvancedSelector:
    """Quick partial text selector"""
    return AdvancedSelector(type=SelectorType.CONTAINS_TEXT, value=value)
