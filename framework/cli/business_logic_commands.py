"""
CLI commands for business logic analysis
"""

import json
from pathlib import Path
from typing import Dict

import click
import yaml


@click.group()
def business() -> None:
    """
    Business logic analysis commands

    Extract and analyze business logic from source code
    """
    pass


@business.command()
@click.option("--source", type=click.Path(exists=True), required=True, help="Path to source code")
@click.option(
    "--output",
    type=click.Path(),
    default="business_logic.yaml",
    help="Output file for analysis results",
)
@click.option("--format", type=click.Choice(["yaml", "json"]), default="yaml", help="Output format")
def analyze(source: str, output: str, format: str) -> None:
    """
    Analyze business logic from source code

    Example:
        observe business analyze --source ./app/src --output business_logic.yaml
    """
    from framework.analyzers.business_logic_analyzer import BusinessLogicAnalyzer

    click.echo("\n🔍 Analyzing business logic...")
    click.echo(f"   Source: {source}")

    analyzer = BusinessLogicAnalyzer(Path(source))
    analysis = analyzer.analyze()

    # Print summary
    click.echo("\n📊 Analysis Summary:")
    click.echo(f"   Platform: {analyzer.platform.upper()}")
    click.echo(f"   User Flows: {len(analysis.user_flows)}")
    click.echo(f"   Business Rules: {len(analysis.business_rules)}")
    click.echo(f"   Data Models: {len(analysis.data_models)}")
    click.echo(f"   State Machines: {len(analysis.state_machines)}")
    click.echo(f"   Edge Cases: {len(analysis.edge_cases)}")
    click.echo(f"   Negative Tests: {len(analysis.negative_test_cases)}")
    click.echo(f"   Mock Data Entities: {len(analysis.mock_data)}")

    # Show user flows
    if analysis.user_flows:
        click.echo("\n👤 User Flows:")
        for flow in analysis.user_flows[:5]:  # Show first 5
            click.echo(f"   • {flow.name}")
            click.echo(f"     Steps: {len(flow.steps)}")
            click.echo(f"     Entry: {flow.entry_point}")
        if len(analysis.user_flows) > 5:
            click.echo(f"   ... and {len(analysis.user_flows) - 5} more")

    # Show state machines
    if analysis.state_machines:
        click.echo("\n🔄 State Machines:")
        for sm in analysis.state_machines[:3]:
            click.echo(f"   • {sm.name}: {len(sm.states)} states")
        if len(analysis.state_machines) > 3:
            click.echo(f"   ... and {len(analysis.state_machines) - 3} more")

    # Show edge cases summary
    if analysis.edge_cases:
        click.echo("\n⚠️ Edge Cases:")
        edge_types: Dict[str, int] = {}
        for ec in analysis.edge_cases:
            edge_types[ec.type] = edge_types.get(ec.type, 0) + 1
        for edge_type, count in edge_types.items():
            click.echo(f"   • {edge_type}: {count} detected")

    # Show data models
    if analysis.data_models:
        click.echo("\n📦 Data Models:")
        for model in analysis.data_models[:5]:
            click.echo(f"   • {model.name} ({len(model.fields)} fields)")
        if len(analysis.data_models) > 5:
            click.echo(f"   ... and {len(analysis.data_models) - 5} more")

    # Show mock data
    if analysis.mock_data:
        click.echo("\n🎭 Mock Test Data:")
        for entity, data in list(analysis.mock_data.items())[:5]:
            if isinstance(data, dict):
                if "start_id" in data and "end_id" in data:
                    # Android mock data with ID ranges
                    click.echo(f"   • {entity}: {data['count']} records (IDs {data['start_id']}-{data['end_id']})")
                elif "type" in data:
                    # iOS mock data without ID ranges
                    click.echo(f"   • {entity}: {data['count']} {data['type']} objects")
                else:
                    # Generic mock data
                    click.echo(f"   • {entity}: {data.get('count', 'N/A')} records")
        if len(analysis.mock_data) > 5:
            click.echo(f"   ... and {len(analysis.mock_data) - 5} more")

    # Show API contracts
    if analysis.api_contracts:
        click.echo("\n📡 API Contracts:")
        for contract in analysis.api_contracts[:5]:
            click.echo(f"   • {contract.method} {contract.endpoint}")
        if len(analysis.api_contracts) > 5:
            click.echo(f"   ... and {len(analysis.api_contracts) - 5} more")

    # Save to file
    output_path = Path(output)
    export_data = analyzer.export_to_json()

    with open(output_path, "w") as f:
        if format == "json":
            json.dump(export_data, f, indent=2)
        else:
            yaml.dump(export_data, f, default_flow_style=False, sort_keys=False)

    click.echo(f"\n💾 Analysis saved to: {output_path}")
    click.echo("\nNext steps:")
    click.echo(f"  1. Review business logic: cat {output_path}")
    click.echo(f"  2. Generate scenarios: observe business scenarios --input {output_path}")
    click.echo(f"  3. Generate BDD features: observe business features --input {output_path}")
    click.echo(f"  4. View API contracts: observe business contracts --input {output_path}")
    click.echo(f"  5. View edge cases: observe business edge-cases --input {output_path}")
    click.echo(f"  6. View negative tests: observe business negative --input {output_path}")


@business.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Business logic analysis file",
)
@click.option(
    "--output",
    type=click.Path(),
    default="test_scenarios.yaml",
    help="Output file for test scenarios",
)
def scenarios(input_file: str, output: str) -> None:
    """
    Generate test scenarios from business logic

    Example:
        observe business scenarios --input business_logic.yaml
    """
    from framework.analyzers.business_logic_analyzer import BusinessLogicAnalyzer

    click.echo("\n🎯 Generating test scenarios...")

    # Load analysis
    with open(input_file) as f:
        if input_file.endswith(".json"):
            data = json.load(f)
        else:
            data = yaml.safe_load(f)

    # Reconstruct analyzer (simplified)
    analyzer = BusinessLogicAnalyzer(Path("."))

    # Load data into analysis
    from framework.analyzers.business_logic_analyzer import (
        UserFlow,
        BusinessLogicAnalysis,
    )

    analysis = BusinessLogicAnalysis()

    for flow_data in data.get("user_flows", []):
        flow = UserFlow(
            name=flow_data["name"],
            description=flow_data["description"],
            steps=flow_data["steps"],
            entry_point=flow_data["entry_point"],
            success_outcome=flow_data["success_outcome"],
            failure_outcomes=flow_data.get("failure_outcomes", []),
            source_files=flow_data.get("source_files", []),
        )
        analysis.user_flows.append(flow)

    analyzer.analysis = analysis

    # Generate scenarios
    scenarios_list = analyzer.generate_test_scenarios()

    click.echo(f"\n✨ Generated {len(scenarios_list)} test scenarios:")
    for scenario in scenarios_list:
        emoji = "✅" if scenario["type"] == "positive" else "❌"
        click.echo(f"   {emoji} {scenario['name']} [{scenario['priority']}]")

    # Save
    output_path = Path(output)
    with open(output_path, "w") as f:
        yaml.dump({"scenarios": scenarios_list}, f, default_flow_style=False)

    click.echo(f"\n💾 Scenarios saved to: {output_path}")


@business.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Business logic analysis file",
)
@click.option(
    "--output",
    type=click.Path(),
    default="features/business_logic.feature",
    help="Output BDD feature file",
)
def features(input_file: str, output: str) -> None:
    """
    Generate BDD feature files from business logic

    Example:
        observe business features --input business_logic.yaml
    """
    from framework.analyzers.business_logic_analyzer import (
        BusinessLogicAnalyzer,
        UserFlow,
        BusinessLogicAnalysis,
    )

    click.echo("\n📝 Generating BDD features...")

    # Load analysis
    with open(input_file) as f:
        if input_file.endswith(".json"):
            data = json.load(f)
        else:
            data = yaml.safe_load(f)

    # Reconstruct analyzer
    analyzer = BusinessLogicAnalyzer(Path("."))
    analysis = BusinessLogicAnalysis()

    for flow_data in data.get("user_flows", []):
        flow = UserFlow(
            name=flow_data["name"],
            description=flow_data["description"],
            steps=flow_data["steps"],
            entry_point=flow_data["entry_point"],
            success_outcome=flow_data["success_outcome"],
            failure_outcomes=flow_data.get("failure_outcomes", []),
            source_files=flow_data.get("source_files", []),
        )
        analysis.user_flows.append(flow)

    analyzer.analysis = analysis

    # Generate feature content
    feature_content = analyzer.generate_bdd_features()

    # Save
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(feature_content)

    click.echo("\n✅ BDD features generated:")
    click.echo(f"   File: {output_path}")
    click.echo(f"   Flows: {len(analysis.user_flows)}")

    click.echo("\nPreview:")
    click.echo("   " + "\n   ".join(feature_content.split("\n")[:15]))
    if len(feature_content.split("\n")) > 15:
        click.echo("   ...")


@business.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Business logic analysis file",
)
def testdata(input_file: str) -> None:
    """
    Show available mock test data

    Example:
        observe business testdata --input business_logic.yaml
    """
    click.echo("\n🎭 Available Mock Test Data:")

    # Load analysis
    with open(input_file) as f:
        if input_file.endswith(".json"):
            data = json.load(f)
        else:
            data = yaml.safe_load(f)

    mock_data = data.get("mock_data", {})

    if not mock_data:
        click.echo("   No mock data found")
        return

    for entity, entity_data in mock_data.items():
        click.echo(f"\n   📦 {entity}")
        if isinstance(entity_data, dict):
            if "start_id" in entity_data and "end_id" in entity_data:
                # Android mock data with ID ranges
                click.echo(f"      Records: {entity_data['count']}")
                click.echo(f"      ID Range: {entity_data['start_id']} - {entity_data['end_id']}")
                click.echo(f"      Source: {entity_data.get('source', 'N/A')}")
                click.echo("\n      💡 Use in tests:")
                click.echo(f"         Valid IDs: {entity_data['start_id']}, {entity_data['start_id'] + 1}, ...")
                click.echo(f"         Invalid ID: {entity_data['end_id'] + 100}")
            elif "type" in entity_data:
                # iOS mock data without ID ranges
                click.echo(f"      Records: {entity_data['count']}")
                click.echo(f"      Type: {entity_data['type']}")
                click.echo(f"      Source: {entity_data.get('source', 'N/A')}")
                click.echo("\n      💡 Use in tests:")
                click.echo(f"         Use array indices: 0, 1, 2, ... {entity_data['count'] - 1}")
                click.echo(f"         Invalid index: {entity_data['count']}")
            else:
                # Generic mock data
                click.echo(f"      Records: {entity_data.get('count', 'N/A')}")
                click.echo(f"      Source: {entity_data.get('source', 'N/A')}")


@business.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Business logic analysis file",
)
def edgecases(input_file: str) -> None:
    """
    Show detected edge cases

    Example:
        observe business edgecases --input business_logic.yaml
    """
    click.echo("\n⚠️ Detected Edge Cases:")

    # Load analysis
    with open(input_file) as f:
        if input_file.endswith(".json"):
            data = json.load(f)
        else:
            data = yaml.safe_load(f)

    edge_cases = data.get("edge_cases", [])

    if not edge_cases:
        click.echo("   No edge cases detected")
        return

    # Group by type
    by_type: Dict[str, list] = {}
    for ec in edge_cases:
        ec_type = ec["type"]
        if ec_type not in by_type:
            by_type[ec_type] = []
        by_type[ec_type].append(ec)

    for ec_type, cases in by_type.items():
        click.echo(f"\n   🔍 {ec_type.upper()} ({len(cases)} cases):")
        for ec in cases[:5]:  # Show first 5 per type
            click.echo(f"      • {ec['description']}")
            click.echo(f"        Severity: {ec['severity']}")
            if ec.get("test_data"):
                click.echo(f"        Test values: {ec['test_data']}")
        if len(cases) > 5:
            click.echo(f"      ... and {len(cases) - 5} more")


@business.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Business logic analysis file",
)
def statemachines(input_file: str) -> None:
    """
    Show extracted state machines

    Example:
        observe business statemachines --input business_logic.yaml
    """
    click.echo("\n🔄 Extracted State Machines:")

    # Load analysis
    with open(input_file) as f:
        if input_file.endswith(".json"):
            data = json.load(f)
        else:
            data = yaml.safe_load(f)

    state_machines = data.get("state_machines", [])

    if not state_machines:
        click.echo("   No state machines detected")
        return

    for sm in state_machines:
        click.echo(f"\n   📊 {sm['name']}")
        click.echo(f"      States: {', '.join(sm['states'])}")
        click.echo(f"      Initial: {sm['initial_state']}")

        if sm.get("transitions"):
            click.echo("      Transitions:")
            for from_state, to_states in sm["transitions"].items():
                if to_states:
                    click.echo(f"        {from_state} → {', '.join(to_states)}")


@business.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Business logic analysis file",
)
@click.option(
    "--output",
    type=click.Path(),
    default="negative_tests.yaml",
    help="Output file for negative test cases",
)
def negative(input_file: str, output: str) -> None:
    """
    Show generated negative test cases

    Example:
        observe business negative --input business_logic.yaml
    """
    click.echo("\n❌ Generated Negative Test Cases:")

    # Load analysis
    with open(input_file) as f:
        if input_file.endswith(".json"):
            data = json.load(f)
        else:
            data = yaml.safe_load(f)

    negative_tests = data.get("negative_test_cases", [])

    if not negative_tests:
        click.echo("   No negative test cases generated")
        return

    click.echo(f"\n   Total: {len(negative_tests)} test cases")

    # Group by priority
    by_priority: Dict[str, list] = {}
    for test in negative_tests:
        priority = test.get("priority", "medium")
        if priority not in by_priority:
            by_priority[priority] = []
        by_priority[priority].append(test)

    for priority in ["critical", "high", "medium", "low"]:
        if priority in by_priority:
            tests = by_priority[priority]
            click.echo(f"\n   🔴 {priority.upper()} Priority ({len(tests)} tests):")
            for test in tests[:5]:
                click.echo(f"      • {test['name']}")
                click.echo(f"        Outcome: {test['expected_outcome']}")
            if len(tests) > 5:
                click.echo(f"      ... and {len(tests) - 5} more")

    # Save to file
    output_path = Path(output)
    with open(output_path, "w") as f:
        yaml.dump({"negative_test_cases": negative_tests}, f, default_flow_style=False)

    click.echo(f"\n💾 Negative tests saved to: {output_path}")


@business.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Business logic analysis file",
)
def contracts(input_file: str) -> None:
    """
    Show extracted API contracts

    Example:
        observe business contracts --input business_logic.yaml
    """
    click.echo("\n📡 Extracted API Contracts:")

    # Load analysis
    with open(input_file) as f:
        if input_file.endswith(".json"):
            data = json.load(f)
        else:
            data = yaml.safe_load(f)

    api_contracts = data.get("api_contracts", [])

    if not api_contracts:
        click.echo("   No API contracts found")
        return

    click.echo(f"\n   Total: {len(api_contracts)} endpoints")

    for contract in api_contracts:
        click.echo(f"\n   🔗 {contract['method']} {contract['endpoint']}")

        if contract.get("description"):
            click.echo(f"      Description: {contract['description']}")

        if contract.get("authentication"):
            click.echo(f"      Auth: {contract['authentication']}")

        if contract.get("request_schema"):
            click.echo("      Request:")
            req = contract["request_schema"]
            if "body" in req:
                click.echo(f"        Body: {req['body']}")
            if "query" in req:
                click.echo(f"        Query params: {req['query']}")
            if "path" in req:
                click.echo(f"        Path params: {req['path']}")

        if contract.get("response_schema"):
            resp = contract["response_schema"]
            if isinstance(resp, dict) and "type" in resp:
                click.echo(f"      Response: {resp['type']}")

        if contract.get("error_responses"):
            errors = contract["error_responses"]
            if len(errors) > 0:
                click.echo(f"      Errors: {len(errors)} defined")

        if contract.get("source_file"):
            click.echo(f"      Source: {contract['source_file']}")


@business.command()
@click.option(
    "--source",
    type=click.Path(exists=True),
    required=True,
    help="Path to source code",
)
@click.option(
    "--output",
    type=click.Path(),
    default="ast_analysis.yaml",
    help="Output file",
)
@click.option(
    "--format",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Output format",
)
def complexity(source: str, output: str, format: str) -> None:
    """
    Analyze code complexity using AST

    Example:
        observe business complexity --source ./framework --output complexity.yaml
    """
    from framework.analyzers.ast_analyzer import ASTAnalyzer

    click.echo("\n🔬 Analyzing code complexity with AST...")
    click.echo(f"   Source: {source}")

    analyzer = ASTAnalyzer(Path(source))
    result = analyzer.analyze_python()

    # Print summary
    summary = result["summary"]
    click.echo("\n📊 Complexity Summary:")
    click.echo(f"   Total Functions: {summary['total_functions']}")
    click.echo(f"   High Complexity (>10): {summary['high_complexity_functions']}")
    click.echo(f"   Average Complexity: {summary['average_complexity']:.2f}")

    # Show top 10 most complex functions
    functions = result["functions"]
    if functions:
        click.echo("\n🎯 Most Complex Functions:")
        sorted_funcs = sorted(
            functions,
            key=lambda f: f["cyclomatic_complexity"],
            reverse=True,
        )
        for func in sorted_funcs[:10]:
            click.echo(
                f"   • {func['name']}: "
                f"CC={func['cyclomatic_complexity']}, "
                f"CogC={func['cognitive_complexity']}, "
                f"Depth={func['nested_depth']}"
            )

    # Save to file
    output_path = Path(output)
    with open(output_path, "w") as f:
        if format == "json":
            json.dump(result, f, indent=2)
        else:
            yaml.dump(result, f, default_flow_style=False)

    click.echo(f"\n💾 Analysis saved to: {output_path}")
    click.echo("\nRecommendations:")
    if summary["high_complexity_functions"] > 0:
        click.echo(f"  ⚠️  {summary['high_complexity_functions']} functions " "have high complexity (CC > 10)")
        click.echo("  💡 Consider refactoring these functions")
    else:
        click.echo("  ✅ All functions have acceptable complexity")
