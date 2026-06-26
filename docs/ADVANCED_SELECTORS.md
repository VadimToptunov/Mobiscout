# Advanced Selectors

Powerful, flexible selector engine for mobile elements with relationship queries, filters, and fuzzy matching.

## Quick Start

### Simple Selectors

```python
from framework.selectors import by_id, by_text, by_class, contains_text

# By ID
selector = by_id("login_button")

# By text (exact)
selector = by_text("Login")

# By text (fuzzy)
selector = by_text("log", fuzzy=True)  # Matches "Login", "Logout", etc.

# By class
selector = by_class("Button")

# Partial text match
selector = contains_text("Log")
```

### Using Selectors

```python
from framework.selectors import AdvancedSelectorEngine

# Create engine with your elements
engine = AdvancedSelectorEngine(elements)

# Find matching elements
results = engine.find(selector)
```

### Fluent Builder API

```python
from framework.selectors import SelectorBuilder, FilterOperator

selector = (
    SelectorBuilder()
    .by_class("Button")
    .with_attribute("enabled", FilterOperator.EQUALS, True)
    .that_is_visible()
    .with_attribute("text", FilterOperator.CONTAINS, "Login")
    .at_index(0)  # First match
    .build()
)
```

## Features

### 1. Multiple Selector Types

- **ID**: `by_id("login_btn")`
- **Text**: `by_text("Login")` or `by_text("log", fuzzy=True)`
- **Class**: `by_class("Button")` or `by_class("button", fuzzy=True)`
- **Partial Text**: `contains_text("Log")`
- **XPath**: Full XPath support
- **Accessibility ID**: Platform-specific accessibility identifiers

### 2. Filter Operators

```python
from framework.selectors import SelectorFilter, FilterOperator

# Available operators
FilterOperator.EQUALS          # text == "Login"
FilterOperator.NOT_EQUALS      # enabled != False
FilterOperator.CONTAINS        # "Log" in text
FilterOperator.STARTS_WITH     # text.startswith("Submit")
FilterOperator.ENDS_WITH       # text.endswith("Button")
FilterOperator.MATCHES         # Regex: text matches "^Login.*"
FilterOperator.GREATER_THAN    # width > 100
FilterOperator.LESS_THAN       # height < 50
FilterOperator.HAS_ATTRIBUTE   # Attribute exists
```

### 3. Chained Filters

```python
selector = (
    SelectorBuilder()
    .by_class("Button")
    .with_attribute("enabled", FilterOperator.EQUALS, True)
    .with_attribute("visible", FilterOperator.EQUALS, True)
    .with_attribute("text", FilterOperator.CONTAINS, "Submit")
    .build()
)

# Or using helper methods
selector = (
    SelectorBuilder()
    .by_text("Submit")
    .that_is_enabled()      # Shortcut for enabled == True
    .that_is_visible()      # Shortcut for visible == True
    .build()
)
```

### 4. Relationship Selectors

Find elements based on their relationships to other elements:

```python
from framework.selectors import AdvancedSelector, SelectorType

# Find button next to (sibling of) an input field
selector = AdvancedSelector(
    type=SelectorType.CLASS,
    value="Button",
    relationship=SelectorType.SIBLING,
    relationship_target=by_id("username_input")
)

# Find elements with specific parent
selector = AdvancedSelector(
    type=SelectorType.CLASS,
    value="TextView",
    relationship=SelectorType.PARENT,
    relationship_target=by_id("header_layout")
)

# Find all buttons inside a form (descendants)
selector = AdvancedSelector(
    type=SelectorType.CLASS,
    value="Button",
    relationship=SelectorType.ANCESTOR,
    relationship_target=by_id("login_form")
)
```

#### Relationship Types

| Relationship | Description               | Use Case                       |
|--------------|---------------------------|--------------------------------|
| `PARENT`     | Direct parent element     | Find container of an element   |
| `CHILD`      | Direct child elements     | Find inputs inside a form      |
| `SIBLING`    | Elements with same parent | Find button next to input      |
| `ANCESTOR`   | Any parent up the tree    | Find screen containing element |
| `DESCENDANT` | Any child down the tree   | Find all buttons in a layout   |

### 5. Index Selection

When multiple elements match, select a specific one:

```python
# Get first EditText
selector = SelectorBuilder().by_class("EditText").at_index(0).build()

# Get second Button
selector = by_class("Button")
selector.index = 1
```

### 6. Fuzzy Matching

Match elements approximately:

```python
# Fuzzy text: matches "Login", "Logout", "Blog", etc.
selector = by_text("log", fuzzy=True)

# Fuzzy class: matches "EditText", "EditTextView", etc.
selector = by_class("edit", fuzzy=True)
```

### 7. Appium Integration

Convert to Appium selector format:

```python
selector = by_id("login_button")
appium_selector = selector.to_appium(platform="android")
# {"id": "login_button"}

element = driver.find_element(**appium_selector)
```

## Real-World Examples

### Example 1: Login Form

```python
from framework.selectors import SelectorBuilder, FilterOperator, by_id

# Find username input
username = by_id("username_input")

# Find password input
password = by_id("password_input")

# Find enabled login button with text "Login" or "Sign In"
login_button = (
    SelectorBuilder()
    .by_class("Button")
    .that_is_enabled()
    .that_is_visible()
    .build()
)

# Or more specific: button next to password field
login_button = AdvancedSelector(
    type=SelectorType.CLASS,
    value="Button",
    filters=[
        SelectorFilter("enabled", FilterOperator.EQUALS, True),
        SelectorFilter("text", FilterOperator.CONTAINS, "Login")
    ],
    relationship=SelectorType.SIBLING,
    relationship_target=password
)
```

### Example 2: List Items

```python
# Find all list items
list_items = by_class("ListItem")

# Find enabled list items only
enabled_items = (
    SelectorBuilder()
    .by_class("ListItem")
    .that_is_enabled()
    .build()
)

# Find 3rd list item
third_item = (
    SelectorBuilder()
    .by_class("ListItem")
    .at_index(2)  # 0-indexed
    .build()
)
```

### Example 3: Complex Form

```python
# Find submit button inside specific form, that is enabled
submit_button = AdvancedSelector(
    type=SelectorType.CLASS,
    value="Button",
    filters=[
        SelectorFilter("text", FilterOperator.CONTAINS, "Submit"),
        SelectorFilter("enabled", FilterOperator.EQUALS, True)
    ],
    relationship=SelectorType.ANCESTOR,
    relationship_target=by_id("checkout_form")
)
```

## CLI Commands

### Parse Selector

```bash
# Parse ID selector
observe selector parse "#login_button"

# Parse class selector
observe selector parse ".Button"

# Parse text selector
observe selector parse "Login"
```

### Show Examples

```bash
observe selector examples
```

### List Operators

```bash
observe selector operators
```

### List Relationships

```bash
observe selector relationships
```

### Benchmark Performance

```bash
observe selector benchmark
```

## Best Practices

### 1. Start Simple, Add Filters

```python
# Start with basic selector
selector = by_class("Button")

# Add filters as needed
selector = (
    SelectorBuilder()
    .by_class("Button")
    .that_is_enabled()
    .with_attribute("text", FilterOperator.CONTAINS, "Submit")
    .build()
)
```

### 2. Use Relationships for Context

```python
# Instead of complex XPath:
# //android.widget.LinearLayout[@id='form']//android.widget.Button

# Use relationship selectors:
button_in_form = AdvancedSelector(
    type=SelectorType.CLASS,
    value="Button",
    relationship=SelectorType.ANCESTOR,
    relationship_target=by_id("form")
)
```

### 3. Prefer Fuzzy for Resilience

```python
# Exact match (brittle)
selector = by_text("Login")

# Fuzzy match (more resilient)
selector = by_text("log", fuzzy=True)
```

### 4. Use Index for Disambiguation

```python
# When multiple elements match, be explicit
first_button = by_class("Button")
first_button.index = 0

second_button = by_class("Button")
second_button.index = 1
```

### 5. Combine with Self-Healing

Advanced selectors work with self-healing tests:

```python
from framework.healing import SelectorDiscovery
from framework.selectors import by_id, contains_text

# Primary selector
primary = by_id("login_btn")

# Fallback selectors
fallbacks = [
    contains_text("Login"),
    by_class("Button", fuzzy=True)
]

discovery = SelectorDiscovery()
element = discovery.find_with_fallback(primary, fallbacks)
```

## Performance

Advanced selectors are optimized for speed:

- **ID lookup**: ~0.1ms per call
- **Class + filter**: ~0.5ms per call
- **Fuzzy text**: ~2ms per call
- **Relationships**: ~1-3ms per call

Benchmarks on 1,000 elements (see `observe selector benchmark`).

## Comparison with XPath

### Traditional XPath

```python
# Complex, brittle
xpath = '//android.widget.LinearLayout[@resource-id="form"]//android.widget.Button[@enabled="true" and contains(@text, "Submit")]'
```

### Advanced Selectors

```python
# Readable, maintainable
selector = (
    SelectorBuilder()
    .by_class("Button")
    .that_is_enabled()
    .with_attribute("text", FilterOperator.CONTAINS, "Submit")
    .build()
)
```

Benefits:

- ✅ Type-safe (IDE autocomplete)
- ✅ Composable (build from parts)
- ✅ Testable (unit test each filter)
- ✅ Self-documenting (clear intent)
- ✅ Platform-agnostic (works on Android & iOS)

## API Reference

### Classes

- `AdvancedSelector`: Main selector class
- `AdvancedSelectorEngine`: Execution engine
- `SelectorBuilder`: Fluent builder
- `SelectorFilter`: Attribute filter
- `SelectorType`: Enum of selector types
- `FilterOperator`: Enum of filter operators

### Functions

- `by_id(value)`: Create ID selector
- `by_text(value, fuzzy=False)`: Create text selector
- `by_class(value, fuzzy=False)`: Create class selector
- `contains_text(value)`: Create partial text selector

## Roadmap

### Phase 1 (Complete)

- ✅ Core selector types
- ✅ Filter operators
- ✅ Relationship selectors
- ✅ Fluent builder API
- ✅ Fuzzy matching
- ✅ Appium integration

### Phase 2 (Future)

- 🔄 Visual selectors (by image)
- 🔄 AI-powered selectors
- 🔄 Selector recording
- 🔄 Selector optimization
- 🔄 Performance improvements

## Support

- **Examples**: `observe selector examples`
- **Documentation**: See above
- **Tests**: `tests/test_advanced_selectors.py`
