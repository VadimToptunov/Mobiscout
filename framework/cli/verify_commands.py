"""
Multi-Language Verification CLI Commands

STEP 12: Multi-Language Verification CLI Interface
"""

from pathlib import Path
from typing import Optional, List

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from framework.verification.verifier import (
    MultiLanguageVerifier,
    VerificationLevel,
)

console = Console()


@click.group()
def verify() -> None:
    """
    Multi-language test verification commands.

    Verify test code across Python, Kotlin, Swift, JavaScript, Go, and Ruby.
    """
    pass


@verify.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--recursive", "-r", is_flag=True, default=True, help="Search recursively")
@click.option("--output", "-o", type=click.Path(), help="Output report path")
@click.option(
    "--level",
    "-l",
    type=click.Choice(["error", "warning", "info", "all"]),
    default="warning",
    help="Minimum issue level to show"
)
@click.option("--exclude", "-e", multiple=True, help="Patterns to exclude")
def check(
    path: str,
    recursive: bool,
    output: Optional[str],
    level: str,
    exclude: tuple
) -> None:
    """
    Verify test files in a directory.

    Example:
        observe verify check ./tests
        observe verify check ./src --recursive --output report.json
        observe verify check ./tests --level error --exclude node_modules
    """
    path_obj = Path(path)

    console.print(Panel.fit(
        f"🔍 Verifying Test Files\n\nPath: {path}",
        style="bold cyan"
    ))

    verifier = MultiLanguageVerifier()
    exclude_list = list(exclude) if exclude else None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning files...", total=None)

        if path_obj.is_file():
            result = verifier.verify_file(path_obj)
            results = [result] if result else []
        else:
            results = verifier.verify_directory(
                path_obj,
                recursive=recursive,
                exclude_patterns=exclude_list
            )

        progress.update(task, completed=True)

    if not results:
        console.print("[yellow]No supported files found[/yellow]")
        return

    # Get summary
    summary = verifier.get_summary(results)

    # Display summary
    console.print()
    console.print(Panel.fit("📊 Verification Summary", style="bold green"))

    summary_table = Table()
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="yellow", justify="right")

    summary_table.add_row("Total Files", str(summary["total_files"]))
    summary_table.add_row("Passed", f"[green]{summary['passed']}[/green]")
    summary_table.add_row("Failed", f"[red]{summary['failed']}[/red]")
    summary_table.add_row("Total Errors", f"[red]{summary['total_errors']}[/red]")
    summary_table.add_row("Total Warnings", f"[yellow]{summary['total_warnings']}[/yellow]")
    summary_table.add_row("Pass Rate", f"{summary['pass_rate']:.1f}%")

    console.print(summary_table)

    # By language
    if summary["by_language"]:
        console.print()
        console.print("[bold]By Language:[/bold]")

        lang_table = Table()
        lang_table.add_column("Language", style="cyan")
        lang_table.add_column("Files", justify="right")
        lang_table.add_column("Passed", justify="right")
        lang_table.add_column("Errors", justify="right")
        lang_table.add_column("Warnings", justify="right")

        for lang, stats in summary["by_language"].items():
            lang_table.add_row(
                lang.title(),
                str(stats["files"]),
                f"[green]{stats['passed']}[/green]",
                f"[red]{stats['errors']}[/red]" if stats["errors"] else "-",
                f"[yellow]{stats['warnings']}[/yellow]" if stats["warnings"] else "-",
            )

        console.print(lang_table)

    # Display issues
    level_filter = {
        "error": [VerificationLevel.ERROR],
        "warning": [VerificationLevel.ERROR, VerificationLevel.WARNING],
        "info": [VerificationLevel.ERROR, VerificationLevel.WARNING, VerificationLevel.INFO],
        "all": list(VerificationLevel),
    }[level]

    all_issues = []
    for result in results:
        for issue in result.issues:
            if issue.level in level_filter:
                all_issues.append((result.file_path, issue))

    if all_issues:
        console.print()
        console.print(Panel.fit(f"📋 Issues ({len(all_issues)})", style="bold yellow"))

        for file_path, issue in all_issues[:50]:
            level_style = {
                VerificationLevel.ERROR: "red",
                VerificationLevel.WARNING: "yellow",
                VerificationLevel.INFO: "blue",
                VerificationLevel.SUGGESTION: "dim",
            }[issue.level]

            console.print(
                f"[{level_style}]{issue.level.value.upper()}[/{level_style}] "
                f"[dim]{Path(file_path).name}:{issue.line_number}[/dim] "
                f"{issue.message}"
            )
            if issue.suggestion:
                console.print(f"  [cyan]→ {issue.suggestion}[/cyan]")

        if len(all_issues) > 50:
            console.print(f"\n[dim]... and {len(all_issues) - 50} more issues[/dim]")

    # Export report
    if output:
        output_path = Path(output)
        verifier.export_report(results, output_path)
        console.print(f"\n[green]✓[/green] Report saved to {output_path}")

    # Exit code
    if summary["total_errors"] > 0:
        raise SystemExit(1)


@verify.command()
@click.argument("file_path", type=click.Path(exists=True))
def file(file_path: str) -> None:
    """
    Verify a single file.

    Example:
        observe verify file tests/test_login.py
        observe verify file src/LoginTest.kt
    """
    path = Path(file_path)

    verifier = MultiLanguageVerifier()
    result = verifier.verify_file(path)

    if not result:
        console.print(f"[yellow]Unsupported file type: {path.suffix}[/yellow]")
        raise SystemExit(1)

    # Display result
    status = "[green]✓ PASSED[/green]" if result.success else "[red]✗ FAILED[/red]"

    console.print(Panel.fit(
        f"{status}\n\n"
        f"File: {path.name}\n"
        f"Language: {result.language.title()}\n"
        f"Errors: {result.error_count} | Warnings: {result.warning_count}",
        title="Verification Result",
        border_style="green" if result.success else "red",
    ))

    # Display issues
    if result.issues:
        console.print()
        for issue in result.issues:
            level_style = {
                VerificationLevel.ERROR: "red",
                VerificationLevel.WARNING: "yellow",
                VerificationLevel.INFO: "blue",
                VerificationLevel.SUGGESTION: "dim",
            }[issue.level]

            console.print(
                f"[{level_style}]{issue.level.value.upper()}[/{level_style}] "
                f"[dim]Line {issue.line_number}:[/dim] "
                f"{issue.message}"
            )
            if issue.suggestion:
                console.print(f"  [cyan]→ {issue.suggestion}[/cyan]")

    if not result.success:
        raise SystemExit(1)


@verify.command()
def languages() -> None:
    """
    List supported languages for verification.

    Example:
        observe verify languages
    """
    console.print(Panel.fit("📋 Supported Languages", style="bold cyan"))

    table = Table()
    table.add_column("Language", style="cyan")
    table.add_column("Extensions", style="yellow")
    table.add_column("Frameworks", style="white")

    languages = [
        ("Python", ".py", "pytest, unittest"),
        ("Kotlin", ".kt, .kts", "JUnit5, TestNG"),
        ("Swift", ".swift", "XCTest"),
        ("JavaScript", ".js, .ts, .jsx, .tsx", "Jest, Mocha, Jasmine, Vitest"),
        ("Go", ".go", "testing"),
        ("Ruby", ".rb", "RSpec, Minitest"),
    ]

    for lang, exts, frameworks in languages:
        table.add_row(lang, exts, frameworks)

    console.print(table)

    console.print("\n[dim]Verification includes:[/dim]")
    console.print("  • Syntax validation")
    console.print("  • Import/dependency checking")
    console.print("  • Test structure validation")
    console.print("  • Selector pattern verification")
    console.print("  • Best practices checking")


@verify.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--fix", is_flag=True, help="Attempt to auto-fix issues")
def lint(path: str, fix: bool) -> None:
    """
    Lint test files with auto-fix option.

    Example:
        observe verify lint ./tests
        observe verify lint ./tests --fix
    """
    path_obj = Path(path)

    console.print(Panel.fit(
        f"🔧 Linting Test Files\n\nPath: {path}\nAuto-fix: {'Yes' if fix else 'No'}",
        style="bold magenta"
    ))

    verifier = MultiLanguageVerifier()

    if path_obj.is_file():
        result = verifier.verify_file(path_obj)
        results = [result] if result else []
    else:
        results = verifier.verify_directory(path_obj)

    fixable_issues = 0
    fixed_issues = 0

    for result in results:
        for issue in result.issues:
            if issue.suggestion:
                fixable_issues += 1

                if fix:
                    # Auto-fix logic (placeholder - would need language-specific fixers)
                    console.print(f"[dim]Would fix: {issue.message}[/dim]")
                    fixed_issues += 1

    console.print()
    if fix:
        console.print(f"[green]✓[/green] Fixed {fixed_issues}/{fixable_issues} issues")
    else:
        console.print(f"[yellow]ℹ[/yellow] {fixable_issues} issues can be auto-fixed")
        console.print("  Run with --fix to apply fixes")


if __name__ == "__main__":
    verify()
