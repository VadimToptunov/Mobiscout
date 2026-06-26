"""
CLI commands for Advanced Selectors
"""

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from framework.selectors.advanced_selector import (
    AdvancedSelector,
    AdvancedSelectorEngine,
    SelectorType,
    SelectorFilter,
    FilterOperator,
    by_id,
    by_text,
    by_class,
)

console = Console()


@click.group()
def selector():
    """Advanced selector utilities."""
    pass


@selector.command()
@click.argument("selector_string")
@click.option("--platform", default="android", help="Platform (android/ios)")
def parse(selector_string: str, platform: str):
    """Parse and validate a selector string."""
    console.print(f"\n[bold]Parsing selector:[/bold] [cyan]{selector_string}[/cyan]\n")

    try:
        # Simple parsing logic (can be extended)
        if selector_string.startswith("#"):
            # ID selector
            selector = by_id(selector_string[1:])
            selector_type = "ID"
        elif selector_string.startswith("."):
            # Class selector
            selector = by_class(selector_string[1:])
            selector_type = "Class"
        else:
            # Text selector
            selector = by_text(selector_string)
            selector_type = "Text"

        console.print(f"[green]✅ Valid selector![/green]\n")
        console.print(f"Type: [cyan]{selector_type}[/cyan]")
        console.print(f"Value: [cyan]{selector.value}[/cyan]\n")

        # Show Appium conversion
        appium_selector = selector.to_appium(platform)
        console.print("[bold]Appium format:[/bold]")
        console.print(f"  {appium_selector}\n")

    except Exception as e:
        console.print(f"[red]❌ Invalid selector: {e}[/red]")


@selector.command()
def examples():
    """Show selector examples."""
    examples_text = """
# Simple Selectors

from framework.selectors import by_id, by_text, by_class, contains_text

# By ID
selector = by_id("login_button")

# By text (exact match)
selector = by_text("Login")

# By text (fuzzy match)
selector = by_text("log", fuzzy=True)  # Matches "Login", "Logout", etc.

# By class
selector = by_class("Button")

# By partial text
selector = contains_text("Log")  # Matches any text containing "Log"

# Using with Engine
from framework.selectors import AdvancedSelectorEngine

engine = AdvancedSelectorEngine(elements)
results = engine.find(selector)


# Fluent Builder API

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


# Chained Filters

selector = (
    SelectorBuilder()
    .by_text("Submit")
    .that_is_enabled()      # enabled == True
    .that_is_visible()      # visible == True
    .build()
)


# Relationship Selectors

from framework.selectors import AdvancedSelector, SelectorType

# Find button that is sibling of EditText
selector = AdvancedSelector(
    type=SelectorType.CLASS,
    value="Button",
    relationship=SelectorType.SIBLING,
    relationship_target=AdvancedSelector(
        type=SelectorType.CLASS,
        value="EditText"
    )
)

# Find element with specific parent
selector = AdvancedSelector(
    type=SelectorType.CLASS,
    value="TextView",
    relationship=SelectorType.PARENT,
    relationship_target=by_id("header_layout")
)


# Custom Filters

from framework.selectors import SelectorFilter, FilterOperator

selector = AdvancedSelector(
    type=SelectorType.CLASS,
    value="Button",
    filters=[
        SelectorFilter("width", FilterOperator.GREATER_THAN, 100),
        SelectorFilter("text", FilterOperator.STARTS_WITH, "Submit"),
        SelectorFilter("enabled", FilterOperator.HAS_ATTRIBUTE)
    ]
)


# Complex Real-World Example

# Find enabled "Login" button next to username input
username_input = by_id("username")

login_button = (
    SelectorBuilder()
    .contains_text("Login")
    .with_attribute("class", FilterOperator.EQUALS, "Button")
    .that_is_enabled()
    .that_is_visible()
    .with_sibling(username_input)
    .build()
)


# Filter Operators

FilterOperator.EQUALS          # ==
FilterOperator.NOT_EQUALS      # !=
FilterOperator.CONTAINS        # "text" in value
FilterOperator.STARTS_WITH     # value.startswith("text")
FilterOperator.ENDS_WITH       # value.endswith("text")
FilterOperator.MATCHES         # regex match
FilterOperator.GREATER_THAN    # >
FilterOperator.LESS_THAN       # <
FilterOperator.HAS_ATTRIBUTE   # attribute exists


# Appium Conversion

# Convert to Appium format for use with driver
appium_selector = selector.to_appium(platform="android")
element = driver.find_element(**appium_selector)
"""

    syntax = Syntax(examples_text, "python", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title="Selector Examples", border_style="cyan"))


@selector.command()
def operators():
    """List all available filter operators."""
    table = Table(title="Filter Operators")
    table.add_column("Operator", style="cyan")
    table.add_column("Symbol", style="yellow")
    table.add_column("Description")
    table.add_column("Example", style="dim")

    operators_list = [
        ("EQUALS", "==", "Exact match", 'text == "Login"'),
        ("NOT_EQUALS", "!=", "Not equal", 'enabled != False'),
        ("CONTAINS", "contains", "Contains substring", '"Log" in text'),
        ("STARTS_WITH", "starts_with", "Starts with", 'text.startswith("Submit")'),
        ("ENDS_WITH", "ends_with", "Ends with", 'text.endswith("Button")'),
        ("MATCHES", "matches", "Regex match", 'text matches "^Login.*"'),
        ("GREATER_THAN", ">", "Greater than", "width > 100"),
        ("LESS_THAN", "<", "Less than", "height < 50"),
        ("HAS_ATTRIBUTE", "has_attr", "Attribute exists", "element has 'enabled'"),
    ]

    for name, symbol, desc, example in operators_list:
        table.add_row(name, symbol, desc, example)

    console.print(table)


@selector.command()
def relationships():
    """List all available relationship types."""
    table = Table(title="Relationship Selectors")
    table.add_column("Relationship", style="cyan")
    table.add_column("Description")
    table.add_column("Use Case", style="dim")

    relationships_list = [
        ("PARENT", "Direct parent element", "Find container of an element"),
        ("CHILD", "Direct child elements", "Find inputs inside a form"),
        ("SIBLING", "Elements with same parent", "Find button next to input"),
        ("ANCESTOR", "Any parent up the tree", "Find screen containing element"),
        ("DESCENDANT", "Any child down the tree", "Find all buttons in a layout"),
    ]

    for rel, desc, use_case in relationships_list:
        table.add_row(rel, desc, use_case)

    console.print(table)


@selector.command()
def benchmark():
    """Benchmark selector performance."""
    import time

    console.print("\n[bold]Running selector benchmark...[/bold]\n")

    # Create large element hierarchy
    elements = []
    for i in range(1000):
        elements.append(
            {
                "id": f"element_{i}",
                "parent_id": f"element_{i // 10}" if i > 10 else None,
                "class": f"Class{i % 5}",
                "text": f"Text {i}",
                "enabled": i % 2 == 0,
                "visible": i % 3 == 0,
            }
        )

    engine = AdvancedSelectorEngine(elements)

    # Benchmark different selector types
    benchmarks = []

    # Simple ID lookup
    start = time.time()
    for _ in range(100):
        engine.find(by_id("element_500"))
    id_time = time.time() - start
    benchmarks.append(("ID lookup (100x)", f"{id_time * 1000:.2f}ms", f"{id_time * 10:.2f}ms per call"))

    # Class selector with filters
    start = time.time()
    for _ in range(100):
        selector = AdvancedSelector(
            type=SelectorType.CLASS,
            value="Class1",
            filters=[SelectorFilter("enabled", FilterOperator.EQUALS, True)],
        )
        engine.find(selector)
    filter_time = time.time() - start
    benchmarks.append(
        ("Class + filter (100x)", f"{filter_time * 1000:.2f}ms", f"{filter_time * 10:.2f}ms per call")
    )

    # Fuzzy text search
    start = time.time()
    for _ in range(100):
        engine.find(by_text("text", fuzzy=True))
    fuzzy_time = time.time() - start
    benchmarks.append(("Fuzzy text (100x)", f"{fuzzy_time * 1000:.2f}ms", f"{fuzzy_time * 10:.2f}ms per call"))

    # Display results
    table = Table(title=f"Benchmark Results ({len(elements)} elements)")
    table.add_column("Operation", style="cyan")
    table.add_column("Total Time", justify="right")
    table.add_column("Avg Time", justify="right", style="dim")

    for operation, total, avg in benchmarks:
        table.add_row(operation, total, avg)

    console.print(table)
    console.print(f"\n[green]✅ All operations completed successfully[/green]")


if __name__ == "__main__":
    selector()
