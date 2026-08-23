"""`mobiscout grid` — run a generated kit on a cloud device grid.

Bring your own account: the user sets their provider credentials as environment variables;
Mobiscout builds the Appium hub URL + capability block from them at run time and runs the
(unchanged) generated kit against the grid. No Mobiscout backend, nothing stored.
"""

import os
import subprocess
import sys

import click

from framework.cli._gating import CLOUD_GRID, require_feature
from framework.cli.rich_output import console, print_error, print_header, print_info
from framework.cloud_grid import PROVIDERS, MissingCredentials, UnknownProvider, grid_env


@click.group()
def grid() -> None:
    """Run generated kits on a cloud device grid (BrowserStack / Sauce Labs / LambdaTest)."""
    require_feature(CLOUD_GRID, "Cloud device grid")


@grid.command(name="providers")
def grid_providers() -> None:
    """List supported grid providers and the credential env vars each expects."""
    print_header("Cloud grid providers")
    for provider in PROVIDERS.values():
        print_info(f"  {provider.name:12s} credentials: {provider.user_env}, {provider.key_env}")
    console.print(
        "\nCredentials come from these environment variables (bring your own account) — " "Mobiscout never stores them."
    )


@grid.command(name="run")
@click.argument("kit_dir", type=click.Path(exists=True))
@click.option("--provider", required=True, type=click.Choice(sorted(PROVIDERS)), help="Cloud grid provider")
@click.option("--device", required=True, help='Grid device name, e.g. "Google Pixel 7" / "iPhone 15"')
@click.option("--platform", type=click.Choice(["android", "ios"]), default="android", show_default=True)
@click.option("--os-version", "os_version", default=None, help="Device OS version, e.g. 13")
@click.option("--app", default=None, help="Provider app id/url of an uploaded build (bs://…, storage:…, lt://…)")
def grid_run(kit_dir: str, provider: str, device: str, platform: str, os_version: str, app: str) -> None:
    """Run the generated kit in KIT_DIR against a cloud grid device.

    KIT_DIR must be a **python_pytest** kit (this runner invokes ``pytest``). For a
    Java / JS / Maestro kit, run it with that framework's own runner against the same
    ``MOBISCOUT_APPIUM_SERVER`` / ``MOBISCOUT_EXTRA_CAPS`` this command would export.
    """
    from pathlib import Path

    print_header(f"Running {kit_dir} on {provider}")

    kit = Path(kit_dir)
    if not any(kit.glob("test_*.py")) and not any(kit.rglob("test_*.py")):
        print_error(
            f"'{kit_dir}' doesn't look like a python_pytest kit (no test_*.py found). "
            "`grid run` uses pytest; generate a python_pytest kit, or run your Java/JS/Maestro "
            "kit with its own runner using the env this command prints (MOBISCOUT_APPIUM_SERVER)."
        )
        raise click.Abort()

    try:
        env = grid_env(provider, platform, device, os_version=os_version, app=app)
    except (UnknownProvider, MissingCredentials) as exc:
        print_error(str(exc))
        raise click.Abort()

    print_info(f"Device: {device}" + (f" (OS {os_version})" if os_version else ""))
    print_info(f"Hub: {env['MOBISCOUT_APPIUM_SERVER'].split('@')[-1]}")  # never print embedded credentials
    result = subprocess.run(
        [sys.executable, "-m", "pytest", kit_dir, "-v"],
        env={**os.environ, **env},
    )
    raise SystemExit(result.returncode)
