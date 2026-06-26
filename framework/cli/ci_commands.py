"""
CLI commands for CI/CD Integration
"""

from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from framework.ci.templates import get_template, get_filename

console = Console()


@click.group()
def ci():
    """CI/CD integration commands."""
    pass


@ci.command()
@click.argument("ci_system", type=click.Choice(["github", "gitlab", "jenkins", "circleci"]))
@click.option("--type", "-t", "template_type", type=click.Choice(["basic", "parallel", "multiplatform"]),
              default="basic", help="Template type")
@click.option("--output", "-o", type=Path, help="Output file (default: standard location)")
def init(ci_system: str, template_type: str, output: Path):
    """Initialize CI/CD configuration for your project."""
    console.print(f"\n[cyan]🚀 Generating {ci_system.upper()} {template_type} configuration...[/cyan]\n")

    try:
        template = get_template(ci_system, template_type)
        filename = output or Path(get_filename(ci_system))

        # Create parent directories if needed
        filename.parent.mkdir(parents=True, exist_ok=True)

        # Check if file exists
        if filename.exists():
            if not click.confirm(f"File {filename} already exists. Overwrite?"):
                console.print("[yellow]Cancelled[/yellow]")
                return

        # Write template
        with open(filename, "w") as f:
            f.write(template.strip() + "\n")

        console.print(
            Panel(
                f"[green]✅ CI/CD configuration created![/green]\n\n"
                f"File: [cyan]{filename}[/cyan]\n"
                f"Type: {template_type}\n\n"
                f"[bold]Next steps:[/bold]\n"
                f"1. Review and customize the configuration\n"
                f"2. Commit to your repository\n"
                f"3. Push to trigger the pipeline",
                title=f"{ci_system.upper()} Configuration",
                border_style="green",
            )
        )

        # Show preview
        if click.confirm("\nShow file contents?", default=True):
            syntax = Syntax(template, "yaml" if ci_system in ["github", "gitlab", "circleci"] else "groovy",
                            theme="monokai", line_numbers=True)
            console.print("\n")
            console.print(syntax)

    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")


@ci.command()
def list_templates():
    """List all available CI/CD templates."""
    console.print("\n[bold]Available CI/CD Templates[/bold]\n")

    table = Table(title="Templates")
    table.add_column("CI System", style="cyan")
    table.add_column("Template", style="yellow")
    table.add_column("Description")

    templates_info = [
        ("GitHub Actions", "basic", "Simple workflow for running tests"),
        ("GitHub Actions", "parallel", "Matrix strategy for parallel execution (4 shards)"),
        ("GitHub Actions", "multiplatform", "Test on multiple platforms (Android/iOS)"),
        ("GitLab CI", "basic", "Basic test pipeline"),
        ("GitLab CI", "parallel", "Parallel jobs (4 shards)"),
        ("GitLab CI", "multiplatform", "Multi-platform testing with tags"),
        ("Jenkins", "basic", "Basic pipeline"),
        ("Jenkins", "parallel", "Parallel stages (4 shards)"),
        ("CircleCI", "basic", "Basic config"),
        ("CircleCI", "parallel", "Parallel execution with parallelism=4"),
    ]

    for ci_system, template_type, description in templates_info:
        table.add_row(ci_system, template_type, description)

    console.print(table)

    console.print("\n[dim]Usage: observe ci init <system> --type <template>[/dim]")


@ci.command()
@click.argument("ci_system", type=click.Choice(["github", "gitlab", "jenkins", "circleci"]))
@click.option("--type", "-t", "template_type", type=click.Choice(["basic", "parallel", "multiplatform"]),
              default="basic")
def show(ci_system: str, template_type: str):
    """Show a CI/CD template without saving."""
    try:
        template = get_template(ci_system, template_type)

        console.print(f"\n[bold]{ci_system.upper()} {template_type} template:[/bold]\n")

        syntax = Syntax(
            template,
            "yaml" if ci_system in ["github", "gitlab", "circleci"] else "groovy",
            theme="monokai",
            line_numbers=True
        )
        console.print(syntax)

        console.print(f"\n[dim]To save: observe ci init {ci_system} --type {template_type}[/dim]")

    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")


@ci.command()
@click.argument("config_file", type=Path)
def validate(config_file: Path):
    """Validate CI/CD configuration file."""
    if not config_file.exists():
        console.print(f"[red]❌ File not found: {config_file}[/red]")
        return

    console.print(f"\n[cyan]Validating {config_file}...[/cyan]\n")

    try:
        # Determine CI system from filename
        if ".github" in str(config_file):
            ci_system = "GitHub Actions"
            with open(config_file) as f:
                config = yaml.safe_load(f)

            # Check if YAML is empty or invalid
            if config is None:
                console.print("[red]✗[/red] Validation failed!")
                console.print("[red]Error:[/red] YAML file is empty or invalid")
                raise SystemExit(1)

            # Basic validation
            issues = []
            if "name" not in config:
                issues.append("Missing 'name' field")
            if "on" not in config:
                issues.append("Missing 'on' (triggers) field")
            if "jobs" not in config:
                issues.append("Missing 'jobs' field")

        elif config_file.name == ".gitlab-ci.yml":
            ci_system = "GitLab CI"
            with open(config_file) as f:
                config = yaml.safe_load(f)

            # Check if YAML is empty or invalid
            if config is None:
                console.print("[red]✗[/red] Validation failed!")
                console.print("[red]Error:[/red] YAML file is empty or invalid")
                raise SystemExit(1)

            issues = []
            if "stages" not in config:
                issues.append("Missing 'stages' field")

        elif config_file.name == "Jenkinsfile":
            ci_system = "Jenkins"
            with open(config_file) as f:
                content = f.read()

            issues = []
            if "pipeline" not in content:
                issues.append("Missing 'pipeline' block")
            if "stages" not in content:
                issues.append("Missing 'stages'")

        elif ".circleci" in str(config_file):
            ci_system = "CircleCI"
            with open(config_file) as f:
                config = yaml.safe_load(f)

            # Check if YAML is empty or invalid
            if config is None:
                console.print("[red]✗[/red] Validation failed!")
                console.print("[red]Error:[/red] YAML file is empty or invalid")
                raise SystemExit(1)

            issues = []
            if "version" not in config:
                issues.append("Missing 'version' field")
            if "jobs" not in config:
                issues.append("Missing 'jobs' field")

        else:
            console.print("[yellow]⚠️  Unknown CI system, performing basic validation...[/yellow]")
            ci_system = "Unknown"
            issues = []

        # Report results
        if issues:
            console.print(f"[red]❌ Validation failed for {ci_system}:[/red]\n")
            for issue in issues:
                console.print(f"  • {issue}")
        else:
            console.print(f"[green]✅ {ci_system} configuration looks good![/green]")

    except yaml.YAMLError as e:
        console.print(f"[red]❌ YAML parsing error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Validation error: {e}[/red]")


@ci.command()
def quickstart():
    """Show quick start guide for CI/CD integration."""
    guide = """
# CI/CD Quick Start Guide

## 1. Choose Your CI System

- **GitHub Actions**: For GitHub repositories
- **GitLab CI**: For GitLab repositories
- **Jenkins**: For self-hosted CI
- **CircleCI**: For cloud-based CI

## 2. Generate Configuration

```bash
# GitHub Actions (recommended)
observe ci init github --type parallel

# GitLab CI
observe ci init gitlab --type parallel

# Jenkins
observe ci init jenkins --type basic

# CircleCI
observe ci init circleci --type parallel
```

## 3. Template Types

**Basic**: Simple single-worker execution
- Good for: Small test suites (<50 tests)
- Speed: ~1x (no parallelization)

**Parallel**: Multi-worker execution with sharding
- Good for: Medium/large test suites (50-500+ tests)
- Speed: ~4-8x faster
- Uses 4 parallel workers

**Multiplatform**: Test on Android + iOS
- Good for: Cross-platform apps
- Runs tests on both platforms

## 4. Customize (Optional)

Edit the generated file to customize:
- Number of parallel workers/shards
- Python version
- Test directories
- Triggers (when to run)
- Environment variables

## 5. Commit and Push

```bash
git add .github/workflows/tests.yml  # or appropriate file
git commit -m "Add CI/CD configuration"
git push
```

## 6. Monitor Results

- GitHub: Actions tab
- GitLab: CI/CD > Pipelines
- Jenkins: Build history
- CircleCI: Pipelines dashboard

## Examples

### GitHub Actions with 8 parallel jobs:
```yaml
strategy:
  matrix:
    shard: [0, 1, 2, 3, 4, 5, 6, 7]  # 8 jobs
```

### GitLab CI with custom test dir:
```yaml
script:
  - observe parallel run tests/integration/ --workers 4
```

### Jenkins with environment variables:
```groovy
environment {
    APPIUM_SERVER = 'http://localhost:4723'
}
```

## Need Help?

- List templates: `observe ci list-templates`
- Show template: `observe ci show github --type parallel`
- Validate config: `observe ci validate .github/workflows/tests.yml`
"""

    console.print(Panel(guide, title="CI/CD Quick Start", border_style="cyan"))


if __name__ == "__main__":
    ci()
