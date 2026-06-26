"""
Fuzzing CLI Commands

STEP 8: Fuzzing Module - CLI Interface
"""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from framework.fuzzing.fuzzer import (
    FuzzGenerator,
    MutationFuzzer,
    UIFuzzer,
    APIFuzzer,
    FuzzingCampaign,
    InputType,
    FuzzingStrategy,
)

console = Console()


@click.group()
def fuzz() -> None:
    """
    Fuzzing and edge case testing commands.

    Automated testing with random and edge case inputs.
    """
    pass


@fuzz.command()
@click.option(
    "--type", "-t",
    type=click.Choice(["text", "number", "email", "url", "phone", "password", "json"]),
    default="text",
    help="Input type to generate"
)
@click.option("--count", "-n", type=int, default=20, help="Number of inputs to generate")
@click.option("--output", "-o", type=click.Path(), help="Output file for inputs")
def generate(type: str, count: int, output: Optional[str]) -> None:
    """
    Generate fuzzing inputs.

    Example:
        observe fuzz generate --type email --count 50
        observe fuzz generate --type text -o fuzz_inputs.json
    """
    console.print(Panel.fit(
        f"🎲 Generating {count} {type.upper()} Inputs",
        style="bold cyan"
    ))

    generator = FuzzGenerator()
    input_type = InputType(type)
    inputs = generator.generate(input_type, count)

    # Display inputs
    table = Table(title=f"Generated {len(inputs)} Inputs")
    table.add_column("#", style="dim", width=4)
    table.add_column("Value", style="cyan", max_width=60)
    table.add_column("Strategy", style="yellow")
    table.add_column("Pattern", style="magenta")

    for i, fuzz_input in enumerate(inputs[:20], 1):
        value_str = str(fuzz_input.value)[:50]
        if len(str(fuzz_input.value)) > 50:
            value_str += "..."
        table.add_row(
            str(i),
            value_str,
            fuzz_input.strategy.value,
            fuzz_input.metadata.get('pattern', '-'),
        )

    console.print(table)

    if len(inputs) > 20:
        console.print(f"\n[dim]... and {len(inputs) - 20} more inputs[/dim]")

    # Save to file if requested
    if output:
        import json
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = [
            {
                'value': str(inp.value),
                'type': inp.input_type.value,
                'strategy': inp.strategy.value,
                'metadata': inp.metadata,
            }
            for inp in inputs
        ]

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        console.print(f"\n[green]✓[/green] Saved to {output_path}")


@fuzz.command()
@click.argument("input_value")
@click.option("--mutations", "-m", type=int, default=10, help="Number of mutations")
def mutate(input_value: str, mutations: int) -> None:
    """
    Mutate an input value.

    Example:
        observe fuzz mutate "test@example.com" --mutations 20
        observe fuzz mutate "password123"
    """
    console.print(Panel.fit(
        f"🧬 Mutating Input: '{input_value[:30]}...'",
        style="bold magenta"
    ))

    mutator = MutationFuzzer()
    mutated = mutator.mutate(input_value, mutations)

    table = Table(title=f"Generated {len(mutated)} Mutations")
    table.add_column("#", style="dim", width=4)
    table.add_column("Mutated Value", style="cyan")
    table.add_column("Changes", style="yellow")

    for i, fuzz_input in enumerate(mutated, 1):
        original = fuzz_input.metadata.get('original', '')
        mutated_val = str(fuzz_input.value)

        # Count differences
        changes = sum(1 for a, b in zip(original, mutated_val) if a != b)
        changes += abs(len(original) - len(mutated_val))

        table.add_row(str(i), mutated_val[:60], f"{changes} chars")

    console.print(table)


@fuzz.command()
@click.argument("target_id")
@click.option(
    "--input-type", "-t",
    type=click.Choice(["text", "number", "email", "url", "phone", "password"]),
    default="text",
    help="Type of input expected"
)
@click.option("--count", "-n", type=int, default=50, help="Number of fuzz inputs")
@click.option("--output", "-o", type=click.Path(), help="Output file for results")
def ui(target_id: str, input_type: str, count: int, output: Optional[str]) -> None:
    """
    Fuzz a UI text field.

    Example:
        observe fuzz ui username_field --input-type text --count 100
        observe fuzz ui email_input --input-type email -o results.json
    """
    console.print(Panel.fit(
        f"🎯 Fuzzing UI Element: {target_id}",
        style="bold cyan"
    ))

    fuzzer = UIFuzzer()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Fuzzing {target_id}...", total=count)

        results = []
        for i in range(count):
            # Simulate fuzzing (in real implementation, this would interact with device)
            partial_results = fuzzer.fuzz_text_field(
                target_id,
                InputType(input_type),
                count=1
            )
            results.extend(partial_results)
            progress.update(task, advance=1)

    # Get statistics
    stats = fuzzer.get_statistics()

    console.print()
    console.print(Panel.fit("📊 Fuzzing Results", style="bold green"))

    results_table = Table()
    results_table.add_column("Metric", style="cyan")
    results_table.add_column("Value", style="yellow", justify="right")

    results_table.add_row("Total Inputs", str(stats.get('total_inputs', 0)))
    results_table.add_row("Successes", f"[green]{stats.get('successes', 0)}[/green]")
    results_table.add_row("Errors", f"[yellow]{stats.get('errors', 0)}[/yellow]")
    results_table.add_row("Crashes", f"[red]{stats.get('crashes', 0)}[/red]")
    results_table.add_row(
        "Crash Rate",
        f"{stats.get('crash_rate', 0) * 100:.2f}%"
    )
    results_table.add_row(
        "Avg Response Time",
        f"{stats.get('avg_response_time_ms', 0):.2f}ms"
    )

    console.print(results_table)

    # Show crash inputs if any
    crash_inputs = fuzzer.get_crash_inputs()
    if crash_inputs:
        console.print()
        console.print(Panel.fit(
            f"⚠️ {len(crash_inputs)} Crash-Inducing Inputs Found",
            style="bold red"
        ))

        crash_table = Table()
        crash_table.add_column("Input", style="red", max_width=60)
        crash_table.add_column("Pattern", style="yellow")

        for inp in crash_inputs[:5]:
            crash_table.add_row(
                str(inp.value)[:50],
                inp.metadata.get('pattern', '-'),
            )

        console.print(crash_table)

    # Save results
    if output:
        import json
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'target': target_id,
            'input_type': input_type,
            'statistics': stats,
            'crash_inputs': [
                {'value': str(inp.value), 'pattern': inp.metadata.get('pattern')}
                for inp in crash_inputs
            ],
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        console.print(f"\n[green]✓[/green] Results saved to {output_path}")


@fuzz.command()
@click.argument("endpoint")
@click.option("--method", "-m", type=click.Choice(["GET", "POST", "PUT", "DELETE"]), default="POST")
@click.option(
    "--param-type", "-t",
    type=click.Choice(["text", "number", "email", "url", "json"]),
    default="text",
    help="Parameter type to fuzz"
)
@click.option("--count", "-n", type=int, default=100, help="Number of requests")
@click.option("--output", "-o", type=click.Path(), help="Output file for results")
def api(
    endpoint: str,
    method: str,
    param_type: str,
    count: int,
    output: Optional[str]
) -> None:
    """
    Fuzz an API endpoint.

    Example:
        observe fuzz api /api/users --method POST --param-type json
        observe fuzz api /api/login --param-type text --count 200
    """
    console.print(Panel.fit(
        f"🌐 Fuzzing API: {method} {endpoint}",
        style="bold cyan"
    ))

    fuzzer = APIFuzzer()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Fuzzing {endpoint}...", total=count)

        results = fuzzer.fuzz_endpoint(
            method,
            endpoint,
            InputType(param_type),
            count
        )

        progress.update(task, completed=count)

    # Get vulnerable endpoints
    vulnerable = fuzzer.get_vulnerable_endpoints()

    console.print()
    console.print(Panel.fit("📊 API Fuzzing Results", style="bold green"))

    # Overall stats
    total = len(results)
    errors = sum(1 for r in results if r.error)
    crashes = sum(1 for r in results if r.crash)
    avg_time = sum(r.response_time_ms for r in results) / total if total > 0 else 0

    stats_table = Table()
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="yellow", justify="right")

    stats_table.add_row("Total Requests", str(total))
    stats_table.add_row("Successful", f"[green]{total - errors}[/green]")
    stats_table.add_row("Errors", f"[yellow]{errors}[/yellow]")
    stats_table.add_row("Crashes", f"[red]{crashes}[/red]")
    stats_table.add_row("Error Rate", f"{errors / total * 100:.2f}%")
    stats_table.add_row("Avg Response Time", f"{avg_time:.2f}ms")

    console.print(stats_table)

    # Vulnerable endpoints
    if vulnerable:
        console.print()
        console.print(Panel.fit(
            f"⚠️ {len(vulnerable)} Vulnerable Endpoint(s) Found",
            style="bold red"
        ))

        vuln_table = Table()
        vuln_table.add_column("Endpoint", style="red")
        vuln_table.add_column("Error Rate", style="yellow", justify="right")
        vuln_table.add_column("Crashes", style="red", justify="right")

        for v in vulnerable:
            vuln_table.add_row(
                v['endpoint'],
                f"{v['error_rate'] * 100:.1f}%",
                str(v.get('crashes', 0)),
            )

        console.print(vuln_table)

    # Save results
    if output:
        import json
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'endpoint': endpoint,
            'method': method,
            'param_type': param_type,
            'total_requests': total,
            'errors': errors,
            'crashes': crashes,
            'error_rate': errors / total if total > 0 else 0,
            'vulnerable_endpoints': vulnerable,
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        console.print(f"\n[green]✓[/green] Results saved to {output_path}")


@fuzz.command()
@click.option("--config", "-c", type=click.Path(exists=True), help="Campaign config file")
@click.option("--output", "-o", type=click.Path(), required=True, help="Output report path")
def campaign(config: Optional[str], output: str) -> None:
    """
    Run a comprehensive fuzzing campaign.

    Example:
        observe fuzz campaign --config fuzz_config.json --output report.json
        observe fuzz campaign -o campaign_results.json
    """
    console.print(Panel.fit("🚀 Starting Fuzzing Campaign", style="bold magenta"))

    campaign_runner = FuzzingCampaign()

    # Default targets if no config provided
    if config:
        import json
        with open(config, 'r') as f:
            config_data = json.load(f)
        ui_targets = config_data.get('ui_targets', [])
        api_endpoints = config_data.get('api_endpoints', [])
    else:
        # Demo targets
        ui_targets = [
            {'id': 'username_input', 'type': 'text_field', 'input_type': 'text'},
            {'id': 'password_input', 'type': 'text_field', 'input_type': 'password'},
            {'id': 'email_input', 'type': 'text_field', 'input_type': 'email'},
            {'id': 'submit_button', 'type': 'button'},
        ]
        api_endpoints = [
            {'method': 'POST', 'endpoint': '/api/login', 'param_type': 'json'},
            {'method': 'GET', 'endpoint': '/api/users', 'param_type': 'text'},
        ]

    # Run UI campaign
    console.print("\n[bold]Phase 1: UI Fuzzing[/bold]")
    with console.status("[cyan]Running UI fuzzing campaign..."):
        ui_results = campaign_runner.run_ui_campaign(ui_targets)

    console.print(f"  [green]✓[/green] UI fuzzing complete")
    console.print(f"    Targets: {len(ui_targets)}")
    console.print(f"    Inputs: {ui_results.get('total_inputs', 0)}")
    console.print(f"    Crashes: {ui_results.get('crashes', 0)}")

    # Run API campaign
    console.print("\n[bold]Phase 2: API Fuzzing[/bold]")
    with console.status("[cyan]Running API fuzzing campaign..."):
        api_results = campaign_runner.run_api_campaign(api_endpoints)

    console.print(f"  [green]✓[/green] API fuzzing complete")
    console.print(f"    Endpoints: {len(api_endpoints)}")
    console.print(f"    Requests: {api_results.get('total_requests', 0)}")
    console.print(f"    Errors: {api_results.get('errors', 0)}")

    # Summary
    summary = campaign_runner.get_summary()

    console.print()
    console.print(Panel.fit("📊 Campaign Summary", style="bold green"))

    summary_table = Table()
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="yellow", justify="right")

    summary_table.add_row("Total Inputs", str(summary.get('total_inputs', 0)))
    summary_table.add_row("Total Crashes", f"[red]{summary.get('total_crashes', 0)}[/red]")
    summary_table.add_row("Total Errors", f"[yellow]{summary.get('total_errors', 0)}[/yellow]")
    summary_table.add_row("Campaigns Run", str(len(summary.get('campaigns', []))))

    console.print(summary_table)

    # Export report
    output_path = Path(output)
    campaign_runner.export_report(output_path)
    console.print(f"\n[green]✓[/green] Report saved to {output_path}")


@fuzz.command(name="list")
def list_strategies() -> None:
    """
    List available fuzzing strategies.

    Example:
        observe fuzz list
    """
    console.print(Panel.fit("📋 Fuzzing Strategies", style="bold cyan"))

    table = Table()
    table.add_column("Strategy", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Use Case", style="yellow")

    strategies = [
        (
            "Random",
            "Generate completely random inputs",
            "Initial testing, stress testing"
        ),
        (
            "Mutation",
            "Mutate valid inputs to create edge cases",
            "Finding subtle bugs"
        ),
        (
            "Boundary",
            "Test boundary values (min, max, empty)",
            "Input validation testing"
        ),
        (
            "Grammar",
            "Generate inputs based on input grammar",
            "Protocol fuzzing, format testing"
        ),
        (
            "ML-Assisted",
            "Use ML to guide input generation (PRO)",
            "Smart fuzzing, coverage optimization"
        ),
    ]

    for name, desc, use_case in strategies:
        table.add_row(name, desc, use_case)

    console.print(table)

    console.print()
    console.print("[bold]Input Types:[/bold]")

    input_types = [
        ("text", "General text input"),
        ("number", "Numeric values with boundaries"),
        ("email", "Email address formats"),
        ("url", "URL formats"),
        ("phone", "Phone number formats"),
        ("password", "Password strings"),
        ("json", "JSON payloads"),
    ]

    for type_name, desc in input_types:
        console.print(f"  • [cyan]{type_name}[/cyan]: {desc}")


@fuzz.command()
@click.argument("report_path", type=click.Path(exists=True))
def analyze(report_path: str) -> None:
    """
    Analyze fuzzing results.

    Example:
        observe fuzz analyze campaign_results.json
    """
    import json

    with open(report_path, 'r') as f:
        data = json.load(f)

    console.print(Panel.fit("🔍 Fuzzing Analysis", style="bold cyan"))

    # Analyze UI results
    if 'ui' in data:
        ui = data['ui']
        console.print("\n[bold]UI Fuzzing Analysis:[/bold]")

        stats = ui.get('statistics', {})
        crash_rate = stats.get('crash_rate', 0) * 100

        if crash_rate > 5:
            console.print(f"  [red]⚠️ High crash rate: {crash_rate:.2f}%[/red]")
        elif crash_rate > 1:
            console.print(f"  [yellow]⚠️ Moderate crash rate: {crash_rate:.2f}%[/yellow]")
        else:
            console.print(f"  [green]✓ Low crash rate: {crash_rate:.2f}%[/green]")

        # Analyze targets
        for target in ui.get('targets', []):
            if target.get('crashes', 0) > 0:
                console.print(
                    f"  [red]→ {target['id']}: "
                    f"{target['crashes']} crashes in {target['inputs']} inputs[/red]"
                )

    # Analyze API results
    if 'api' in data:
        api = data['api']
        console.print("\n[bold]API Fuzzing Analysis:[/bold]")

        vulnerable = api.get('vulnerable_endpoints', [])
        if vulnerable:
            console.print(f"  [red]⚠️ {len(vulnerable)} vulnerable endpoint(s) found[/red]")
            for v in vulnerable:
                console.print(
                    f"    → {v['endpoint']}: "
                    f"{v['error_rate'] * 100:.1f}% error rate"
                )
        else:
            console.print("  [green]✓ No vulnerable endpoints found[/green]")

    # Recommendations
    console.print("\n[bold]Recommendations:[/bold]")

    if 'ui' in data:
        crash_inputs = []
        for target in data['ui'].get('targets', []):
            if target.get('crashes', 0) > 0:
                crash_inputs.append(target['id'])

        if crash_inputs:
            console.print("  • Review crash-inducing inputs for UI elements:")
            for inp in crash_inputs:
                console.print(f"    - {inp}")

    if 'api' in data and data['api'].get('vulnerable_endpoints'):
        console.print("  • Add input validation to vulnerable endpoints")
        console.print("  • Implement proper error handling")
        console.print("  • Review API rate limiting")


if __name__ == "__main__":
    fuzz()
