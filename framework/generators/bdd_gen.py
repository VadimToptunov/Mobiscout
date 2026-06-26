"""
BDD Generator

Generates Gherkin feature files and pytest-bdd step definitions.
"""

from pathlib import Path
from typing import List

from jinja2 import Template

from framework.model.app_model import Flow

FEATURE_TEMPLATE = """Feature: {{ flow.name }}
  {{ flow.description }}

{% for scenario in flow.scenarios %}
  Scenario: {{ scenario.name }}
{% if scenario.preconditions %}
    Given {{ scenario.preconditions[0] }}
{% for precondition in scenario.preconditions[1:] %}
    And {{ precondition }}
{% endfor %}
{% endif %}
{% for step in scenario.steps %}
    {{ step.keyword }} {{ step.text }}
{% endfor %}
{% if scenario.expected_result %}
    Then {{ scenario.expected_result }}
{% endif %}

{% endfor %}
"""

STEP_DEFINITIONS_TEMPLATE = """
from pytest_bdd import scenarios, given, when, then, parsers
# Import your page objects explicitly (avoid wildcard imports)
# Example: from pages.login_page import LoginPage
# Example: from pages.home_page import HomePage


# Load scenarios
scenarios('{{ feature_file }}')


# Given steps
{% for step in given_steps %}
@given('{{ step.pattern }}')
def {{ step.function_name }}({{ step.params }}):
    \"\"\"{{ step.description }}\"\"\"
    # TODO: Implement
    pass

{% endfor %}

# When steps
{% for step in when_steps %}
@when('{{ step.pattern }}')
def {{ step.function_name }}({{ step.params }}):
    \"\"\"{{ step.description }}\"\"\"
    # TODO: Implement
    pass

{% endfor %}

# Then steps
{% for step in then_steps %}
@then('{{ step.pattern }}')
def {{ step.function_name }}({{ step.params }}):
    \"\"\"{{ step.description }}\"\"\"
    # TODO: Implement
    pass

{% endfor %}
"""


def generate_feature_file(flow: Flow, output_dir: Path) -> Path:
    """
    Generate Gherkin feature file

    Args:
        flow: Flow model with scenarios
        output_dir: Output directory

    Returns:
        Path to generated feature file
    """
    template = Template(FEATURE_TEMPLATE)
    content = template.render(flow=flow)

    output_dir.mkdir(parents=True, exist_ok=True)
    file_name = flow.name.lower().replace(' ', '_') + '.feature'
    file_path = output_dir / file_name
    file_path.write_text(content)

    return file_path


def generate_step_definitions(flow: Flow, feature_file: str, output_dir: Path) -> Path:
    """
    Generate pytest-bdd step definitions

    Args:
        flow: Flow model
        feature_file: Feature file name
        output_dir: Output directory

    Returns:
        Path to generated step file
    """
    # Extract steps from scenarios
    given_steps = []
    when_steps = []
    then_steps = []

    for scenario in flow.scenarios:
        for step in scenario.steps:
            step_data = {
                'pattern': step.text,
                'function_name': _step_to_function_name(step.text),
                'params': 'driver',
                'description': step.text
            }

            if step.keyword == 'Given':
                given_steps.append(step_data)
            elif step.keyword == 'When':
                when_steps.append(step_data)
            elif step.keyword == 'Then':
                then_steps.append(step_data)

    template = Template(STEP_DEFINITIONS_TEMPLATE)
    content = template.render(
        feature_file=feature_file,
        given_steps=given_steps,
        when_steps=when_steps,
        then_steps=then_steps
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    file_name = 'test_' + flow.name.lower().replace(' ', '_') + '.py'
    file_path = output_dir / file_name
    file_path.write_text(content)

    return file_path


def _step_to_function_name(step_text: str) -> str:
    """Convert step text to valid Python function name"""
    # Remove special characters and convert to snake_case
    name = step_text.lower()
    name = name.replace("'", "").replace('"', '')
    name = ''.join(c if c.isalnum() or c == ' ' else '_' for c in name)
    name = '_'.join(name.split())
    return name


def generate_all_features(flows: List[Flow], output_dir: Path) -> List[Path]:
    """
    Generate feature files and step definitions for all flows

    Args:
        flows: List of flow models
        output_dir: Output directory

    Returns:
        List of generated file paths
    """
    generated_files = []

    for flow in flows:
        # Generate feature file
        feature_file = generate_feature_file(flow, output_dir)
        generated_files.append(feature_file)

        # Generate step definitions
        steps_dir = output_dir / "steps"
        step_file = generate_step_definitions(flow, feature_file.name, steps_dir)
        generated_files.append(step_file)

    return generated_files
