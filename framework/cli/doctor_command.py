"""
CLI command for system health checks
"""

import json
import subprocess
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console

from framework.health import SystemDoctor
from framework.health.doctor import CheckStatus, HealthCheck
from framework.cli.rich_output import console


def _install_appium_driver(name: str) -> str:
    """Attempt ``appium driver install <name>``; report success/failure gracefully.

    npm-backed installs can fail for a hundred reasons (offline, permissions, a
    missing appium binary). Any of those is caught and turned into a readable line
    rather than crashing ``doctor --fix``.
    """
    try:
        proc = subprocess.run(
            ["appium", "driver", "install", name],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return f"Could not install Appium driver '{name}': {e}"
    if proc.returncode == 0:
        return f"Installed Appium driver '{name}'."
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    reason = tail[-1] if tail else "unknown error"
    return f"Failed to install Appium driver '{name}' (npm may have failed): {reason}"


def apply_fixes(checks: List[HealthCheck], out: Console) -> List[str]:
    """Apply the safe, non-destructive fixes for the checks that FAILED or WARNed.

    * ANDROID_HOME — self-heal *this* process's env via ``ensure_android_home`` and
      PRINT the exact ``export`` line to persist it (we never edit shell profiles).
    * A missing required Appium driver — attempt ``appium driver install <name>``,
      surviving an npm failure.

    Only failed/warned checks are acted on; passing checks are left alone. Nothing
    here is destructive. Returns the report lines (also printed to ``out``).
    """
    from framework.health.preflight import ensure_android_home

    lines: List[str] = []
    actionable = [c for c in checks if c.status in (CheckStatus.FAIL, CheckStatus.WARN)]

    # 1) ANDROID_HOME self-heal (only when the SDK check needs attention).
    if any(c.name == "Android SDK" for c in actionable):
        detected = ensure_android_home()
        if detected:
            lines.append(f"ANDROID_HOME self-healed for this process: {detected}")
            lines.append(f"To persist across shells, add to your shell profile: export ANDROID_HOME={detected}")
        else:
            lines.append("Could not self-heal ANDROID_HOME: no Android SDK found. Install it, then set ANDROID_HOME.")

    # 2) Missing required Appium driver — install it.
    for c in actionable:
        if c.fix_command and c.fix_command.startswith("appium driver install"):
            name = c.fix_command.rsplit(" ", 1)[-1]
            lines.append(_install_appium_driver(name))

    if not lines:
        lines.append("No safe automatic fixes to apply.")

    out.print("\n[bold yellow]Applying fixes...[/bold yellow]")
    for line in lines:
        out.print(f"  • {line}")
    return lines


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--export", "-o", type=Path, help="Export results to JSON file")
@click.option("--fix", is_flag=True, help="Apply safe fixes for failed/warned checks (self-heal env, install drivers)")
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
        mobiscout doctor
        mobiscout doctor --verbose
        mobiscout doctor --export health.json
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

        with open(export, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        console.print(f"\n[green]✓[/green] Report exported to {export}")

    # Apply safe fixes for anything that failed/warned (self-heal env, install drivers).
    if fix:
        apply_fixes(checks, console)

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
