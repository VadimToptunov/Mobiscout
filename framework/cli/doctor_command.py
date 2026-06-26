"""
CLI command for system health checks
"""

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from framework.health import SystemDoctor

console = Console()


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--export", "-o", type=Path, help="Export results to JSON file")
@click.option("--fix", is_flag=True, help="Show fix commands for failed checks")
def doctor(verbose: bool, export: Optional[Path], fix: bool) -> None:
    """
    Run system health checks.

    Verifies:
    - Python version
    - Required packages
    - Git configuration
    - Device connectivity
    - File permissions
    - Performance

    Example:
        observe doctor
        observe doctor --verbose
        observe doctor --export health.json
    """
    console.print("\n[bold cyan]🏥 Running System Health Check...[/bold cyan]\n")

    doctor_instance = SystemDoctor(console)
    checks = doctor_instance.run_all_checks(verbose=verbose)

    # Print report
    doctor_instance.print_report(verbose=verbose)

    # Export if requested
    if export:
        data = {
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.name,
                    "message": c.message,
                    "fix_command": c.fix_command,
                }
                for c in checks
            ],
            "summary": {
                "passed": sum(1 for c in checks if c.status.name == "PASS"),
                "failed": sum(1 for c in checks if c.status.name == "FAIL"),
                "warned": sum(1 for c in checks if c.status.name == "WARN"),
                "skipped": sum(1 for c in checks if c.status.name == "SKIP"),
            },
        }

        with open(export, "w") as f:
            json.dump(data, f, indent=2)

        console.print(f"\n[green]✓[/green] Report exported to {export}")

    # Exit with appropriate code
    _passed, failed, warned, _skipped = doctor_instance.generate_report()

    if failed > 0:
        raise SystemExit(1)
    elif warned > 0:
        raise SystemExit(0)  # Warnings don't fail CI
    else:
        raise SystemExit(0)


if __name__ == "__main__":
    doctor()
