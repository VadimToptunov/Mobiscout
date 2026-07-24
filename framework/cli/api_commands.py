"""``mobiscout api`` — analyze captured API traffic (HAR) into test assertions.

Wires the API-log analyzer (``framework.api_analyzer``) to the CLI: point it at a
HAR capture from a proxy (the framework's own ``mock`` proxy, mitmproxy, Charles,
DevTools) and it surfaces the call patterns and proposes assertions you can drop
into API tests.
"""

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from framework.cli.rich_output import print_error, print_header, print_info, print_success

console = Console()


@click.group(name="api")
def api() -> None:
    """🌐 Analyze captured API traffic (HAR)."""


@api.command()
@click.argument("har_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--output", "-o", type=click.Path(), default=None, help="Directory to write full reports (HAR + assertions JSON)."
)
@click.option(
    "--min-confidence", default=0.7, type=float, show_default=True, help="Minimum confidence for a generated assertion."
)
def analyze(har_file: str, output: Optional[str], min_confidence: float) -> None:
    """Analyze a HAR capture: surface API call patterns and generate assertions."""
    from framework.api_analyzer.api_log_analyzer import APIAnalyzer
    from framework.api_analyzer.har import load_har_calls

    print_header("Analyzing API traffic", har_file)

    calls = load_har_calls(Path(har_file))
    if not calls:
        print_error("No modelled API calls found in the HAR.")
        raise click.Abort()

    analyzer = APIAnalyzer()
    for call in calls:
        analyzer.add_api_call(call)

    patterns = analyzer.analyze_patterns()
    assertions = analyzer.generate_assertions(min_confidence=min_confidence)

    print_info(f"Parsed {patterns['total_calls']} API call(s) across {len(patterns['by_endpoint'])} endpoint(s)")

    if assertions:
        table = Table(title=f"{len(assertions)} generated assertion(s)")
        table.add_column("API", style="cyan", overflow="fold")
        table.add_column("Assertion", style="green")
        table.add_column("Expected")
        table.add_column("Conf.", justify="right")
        for assertion in assertions:
            table.add_row(
                assertion.api_call,
                assertion.assertion_type,
                str(assertion.expected_value),
                f"{assertion.confidence:.0%}",
            )
        console.print(table)
    else:
        print_info("No assertions met the confidence threshold.")

    if output:
        out = Path(output)
        out.mkdir(parents=True, exist_ok=True)
        analyzer.export_har(out / "api_calls.har")
        (out / "assertions.json").write_text(
            json.dumps(
                [
                    {
                        "api_call": a.api_call,
                        "assertion_type": a.assertion_type,
                        "expected_value": a.expected_value,
                        "confidence": a.confidence,
                        "reason": a.reason,
                    }
                    for a in assertions
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        print_success(f"✅ Reports written to {out}")
