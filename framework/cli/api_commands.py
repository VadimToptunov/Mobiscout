"""``mobiscout api`` — analyze captured API traffic (HAR) into test assertions.

Wires the API-log analyzer (``framework.api_analyzer``) to the CLI: point it at a
HAR capture from a proxy (the framework's own ``mock`` proxy, mitmproxy, Charles,
DevTools) and it surfaces the call patterns and proposes assertions you can drop
into API tests.
"""

import json
from pathlib import Path
from typing import Any, Optional

import click
from rich.table import Table

from framework.cli.rich_output import print_error, print_header, print_info, print_success, console


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
@click.option(
    "--emit-tests",
    type=click.Path(),
    default=None,
    help="Also generate runnable pytest API tests from the captured traffic into this directory.",
)
def analyze(har_file: str, output: Optional[str], min_confidence: float, emit_tests: Optional[str]) -> None:
    """Analyze a HAR capture: surface API call patterns and generate assertions.

    With --emit-tests, the captured traffic is turned into runnable pytest+requests
    tests that assert the status each endpoint actually returned.
    """
    from framework.api_analyzer.api_log_analyzer import APIAnalyzer
    from framework.api_analyzer.har import load_har_calls

    print_header("Analyzing API traffic", har_file)

    calls = load_har_calls(Path(har_file))
    if not calls:
        print_error("No modelled API calls found in the HAR.")
        raise click.Abort()

    if emit_tests:
        from types import SimpleNamespace

        from framework.codegen.api_test import emit_api_tests
        from framework.codegen.source_api_adapter import base_url_from_har, har_calls_to_api_calls

        api_calls = har_calls_to_api_calls(calls)
        app_model: Any = SimpleNamespace(api_calls={c.name: c for c in api_calls})
        files = emit_api_tests(app_model, base_url=base_url_from_har(calls))
        tests_dir = Path(emit_tests)
        for filename, content in files.items():
            dest = tests_dir / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")
        print_success(f"✅ Generated API tests from captured traffic: {tests_dir}")

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
