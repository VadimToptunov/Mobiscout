"""
Configuration Management CLI Commands

Commands for managing framework configuration with YAML/JSON support,
profiles, environment variables, and validation.
"""

from pathlib import Path
from typing import Optional, Union

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from framework.config import ConfigManager, ObserveConfig

console = Console()


@click.group()
def config() -> None:
    """
    Configuration management commands.

    Manage framework settings, profiles, and integrations.
    """
    pass


@config.command()
@click.option("--path", "-p", type=Path, default=Path(".observe.yaml"), help="Config file path")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config")
def init(path: Path, force: bool) -> None:
    """
    Initialize default configuration file.

    Example:
        observe config init
        observe config init --path custom.yaml
        observe config init --force
    """
    if path.exists() and not force:
        console.print(f"[yellow]⚠[/yellow] Config already exists: {path}")
        console.print("Use --force to overwrite")
        raise SystemExit(1)

    # If force is True and file exists, delete it first
    if force and path.exists():
        path.unlink()
        console.print(f"[yellow]→[/yellow] Removed existing config: {path}")

    manager = ConfigManager(config_path=path)
    manager.init_default()

    console.print(f"[green]✓[/green] Created configuration file: {path}")
    console.print("\n[dim]Edit the file to customize settings[/dim]")


@config.command()
@click.argument("key")
@click.argument("value")
@click.option("--config", "-c", type=Path, help="Config file path")
def set(key: str, value: str, config: Optional[Path]) -> None:
    """
    Set configuration value.

    KEY: Dot-notation key (e.g., framework.timeout)
    VALUE: New value

    Example:
        observe config set framework.timeout 60
        observe config set ml.contribute false
        observe config set integrations.slack.webhook_url "https://..."
    """
    manager = ConfigManager(config_path=config)

    # Convert value to appropriate type
    converted_value: Union[int, float, bool, str]
    if value.lower() in ["true", "false"]:
        converted_value = value.lower() == "true"
    elif value.isdigit():
        converted_value = int(value)
    elif value.replace(".", "", 1).isdigit():
        converted_value = float(value)
    else:
        converted_value = value

    try:
        manager.set(key, converted_value)
        console.print(f"[green]✓[/green] Set {key} = {converted_value}")
    except ValueError as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise SystemExit(1)


@config.command()
@click.argument("key")
@click.option("--config", "-c", type=Path, help="Config file path")
def get(key: str, config: Optional[Path]) -> None:
    """
    Get configuration value.

    KEY: Dot-notation key (e.g., framework.timeout)

    Example:
        observe config get framework.timeout
        observe config get ml.confidence_threshold
    """
    manager = ConfigManager(config_path=config)

    value = manager.get(key)

    if value is None:
        console.print(f"[yellow]⚠[/yellow] Key not found: {key}")
        raise SystemExit(1)

    console.print(f"{key} = [cyan]{value}[/cyan]")


@config.command(name="list")
@click.option("--config", "-c", type=Path, help="Config file path")
@click.option("--format", "-f", type=click.Choice(["table", "yaml", "json"]), default="table", help="Output format")
def list_config(config: Optional[Path], format: str) -> None:
    """
    List all configuration values.

    Example:
        observe config list
        observe config list --format yaml
        observe config list --format json
    """
    manager = ConfigManager(config_path=config)
    config_data = manager.list_all()

    if format == "yaml":
        yaml_str = yaml.dump(config_data, default_flow_style=False)
        syntax = Syntax(yaml_str, "yaml", theme="monokai")
        console.print(syntax)

    elif format == "json":
        import json

        json_str = json.dumps(config_data, indent=2)
        syntax = Syntax(json_str, "json", theme="monokai")
        console.print(syntax)

    else:  # table
        _print_config_table(config_data)


def _print_config_table(config_data: dict, prefix: str = "") -> None:
    """Print configuration as nested tables"""
    for section, values in config_data.items():
        if isinstance(values, dict):
            table = Table(title=f"{prefix}{section}" if prefix else section, show_header=True)
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="green")

            for key, value in values.items():
                if isinstance(value, dict):
                    # Recursively handle nested dicts
                    _print_config_table({key: value}, prefix=f"{section}.")
                else:
                    table.add_row(key, str(value))

            if table.row_count > 0:
                console.print(table)
                console.print()


@config.command()
@click.option("--config", "-c", type=Path, help="Config file path")
def validate(config: Optional[Path]) -> None:
    """
    Validate configuration file.

    Checks:
    - Required fields
    - Value ranges
    - Integration settings

    Example:
        observe config validate
    """
    manager = ConfigManager(config_path=config)
    errors = manager.validate()

    if not errors:
        console.print("[green]✓[/green] Configuration is valid")
        raise SystemExit(0)

    console.print("[red]✗[/red] Configuration validation failed:\n")
    for error in errors:
        console.print(f"  • [red]{error}[/red]")

    raise SystemExit(1)


@config.command()
@click.option("--config", "-c", type=Path, help="Config file path")
def show(config: Optional[Path]) -> None:
    """
    Show configuration file content with syntax highlighting.

    Example:
        observe config show
    """
    manager = ConfigManager(config_path=config)

    if not manager.config_path.exists():
        console.print(f"[yellow]⚠[/yellow] Config file not found: {manager.config_path}")
        console.print("Run [cyan]observe config init[/cyan] to create one")
        raise SystemExit(1)

    with open(manager.config_path, "r") as f:
        content = f.read()

    syntax = Syntax(content, manager.config_path.suffix[1:], theme="monokai", line_numbers=True)

    panel = Panel(
        syntax,
        title=f"Configuration: {manager.config_path}",
        border_style="cyan",
    )

    console.print(panel)


@config.command()
@click.option("--config", "-c", type=Path, help="Config file path")
def path(config: Optional[Path]) -> None:
    """
    Show configuration file path.

    Example:
        observe config path
    """
    manager = ConfigManager(config_path=config)

    if manager.config_path.exists():
        status = "[green]exists[/green]"
    else:
        status = "[yellow]not found[/yellow]"

    console.print(f"Config path: [cyan]{manager.config_path}[/cyan] ({status})")


@config.command()
@click.argument("key")
@click.option("--config", "-c", type=Path, help="Config file path")
def reset(key: str, config: Optional[Path]) -> None:
    """
    Reset configuration value to default.

    KEY: Dot-notation key (e.g., framework.timeout)

    Example:
        observe config reset framework.timeout
    """
    manager = ConfigManager(config_path=config)
    default_config = ObserveConfig()

    default_value = default_config.get(key)

    if default_value is None:
        console.print(f"[red]✗[/red] Invalid key: {key}")
        raise SystemExit(1)

    try:
        manager.set(key, default_value)
        console.print(f"[green]✓[/green] Reset {key} to default: {default_value}")
    except ValueError as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    config()
