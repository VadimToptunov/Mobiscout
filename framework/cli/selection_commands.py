"""
Test Selection CLI commands

Commands for intelligent test selection based on code changes.
"""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from framework.cli.rich_output import print_header, print_info, print_success, print_error
from framework.selection.change_analyzer import ChangeAnalyzer, FileChange
from framework.selection.test_selector import TestSelector

console = Console()


@click.group(name='select')
def select() -> None:
    """🎯 Intelligent test selection commands"""
    pass


@select.command()
@click.option('--since', '-s', default='HEAD~1', help='Git commit to compare against')
@click.option('--tests', '-t', 'tests_dir', type=click.Path(exists=True), default='tests/',
              help='Tests directory')
@click.option('--output', '-o', type=click.Path(), help='Output file for selected tests')
def auto(since: str, tests_dir: str, output: str) -> None:
    """Automatically select tests based on recent code changes"""
    print_header("Intelligent Test Selection")

    print_info(f"Comparing against: {since}")
    print_info(f"Tests directory: {tests_dir}")

    try:
        # Initialize selector and analyzer
        selector = TestSelector(project_root=Path('.'), test_root=Path(tests_dir))
        analyzer = ChangeAnalyzer(repo_path=Path('.'))

        print_info("\n🔄 Analyzing changes...")

        # Get changed files using ChangeAnalyzer
        print_info("  • Detecting changed files")
        base_ref = since if since else "main"
        changes = analyzer.get_changes(base_ref, "HEAD")

        if not changes:
            print_success("\n✅ No changes detected - no tests need to run")
            return

        print_info(f"  • Found {len(changes)} changed files")

        # Select tests
        print_info("  • Selecting affected tests")
        selected_tests = selector.select_tests(changes)

        if not selected_tests:
            print_info("\n⚠️  No tests affected by changes")
            print_info("Consider running smoke tests or all tests")
            return

        # Display results
        print_success(f"\n✅ Selected {len(selected_tests)} tests to run")

        table = Table(title="Selected Tests")
        table.add_column("Test", style="cyan")
        table.add_column("Priority", style="yellow")
        table.add_column("Reason", style="green")

        for test in selected_tests[:15]:  # Show top 15
            table.add_row(
                str(test.test_file),
                test.impact_level.value,
                test.reasons[0] if test.reasons else "Code change"
            )

        console.print(table)

        if len(selected_tests) > 15:
            print_info(f"\n... and {len(selected_tests) - 15} more tests")

        # Time estimation
        if hasattr(selector, 'estimate_duration'):
            estimated_time = selector.estimate_duration(selected_tests)
            print_info(f"\n⏱️  Estimated execution time: {estimated_time:.1f}s")

        # Save to file if requested
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                for test in selected_tests:
                    f.write(f"{test.test_file}::{test.test_name}\n")

            print_success(f"\n✅ Test list saved to: {output_path}")
            print_info(f"Run with: pytest $(cat {output_path})")

    except Exception as e:
        print_error(f"Test selection failed: {e}")
        raise click.Abort()


@select.command(name='by-files')
@click.option('--files', '-f', required=True, help='Comma-separated list of changed files')
@click.option('--tests', '-t', 'tests_dir', type=click.Path(exists=True), default='tests/',
              help='Tests directory')
def by_files(files: str, tests_dir: str) -> None:
    """Select tests based on specific file changes"""
    print_header("Test Selection by Files")

    changed_files = [f.strip() for f in files.split(',')]
    print_info(f"Changed files: {len(changed_files)}")

    for f in changed_files:
        print_info(f"  • {f}")

    try:
        selector = TestSelector(project_root=Path('.'), test_root=Path(tests_dir))

        print_info("\n🔄 Analyzing impact...")

        # Convert string file paths to FileChange objects
        file_changes = [
            FileChange(path=Path(f), change_type=None)  # type: ignore
            for f in changed_files
        ]

        selected_tests = selector.select_tests(file_changes)

        if not selected_tests:
            print_info("\n⚠️  No tests affected by these files")
            return

        print_success(f"\n✅ Selected {len(selected_tests)} tests")

        for test in selected_tests[:10]:
            print_info(f"  • {test.test_file}::{test.test_name}")

        if len(selected_tests) > 10:
            print_info(f"  ... and {len(selected_tests) - 10} more")

    except Exception as e:
        print_error(f"Test selection failed: {e}")
        raise click.Abort()


@select.command()
@click.option('--tests', '-t', 'tests_dir', type=click.Path(exists=True), default='tests/',
              help='Tests directory')
@click.option('--changed-files', '-c', help='Comma-separated list of changed files')
def estimate(tests_dir: str, changed_files: str) -> None:
    """Estimate test execution time"""
    print_header("Test Execution Time Estimation")

    try:
        selector = TestSelector(project_root=Path('.'), test_root=Path(tests_dir))

        if changed_files:
            files = [f.strip() for f in changed_files.split(',')]

            # Convert to FileChange objects
            file_changes = [
                FileChange(path=Path(f), change_type=None)  # type: ignore
                for f in files
            ]

            selected_tests = selector.select_tests(file_changes)
            print_info(f"Selected tests: {len(selected_tests)}")
        else:
            # Estimate all tests
            print_info("Estimating all tests...")
            selected_tests = []  # Would load all tests

        # Time estimation (placeholder logic)
        estimated_seconds = len(selected_tests) * 5  # Assume 5s per test
        estimated_minutes = estimated_seconds / 60

        print_success("\n⏱️  Estimated Execution Time:")
        if estimated_minutes < 1:
            print_info(f"  {estimated_seconds:.0f} seconds")
        elif estimated_minutes < 60:
            print_info(f"  {estimated_minutes:.1f} minutes")
        else:
            hours = estimated_minutes / 60
            print_info(f"  {hours:.1f} hours")

        # Time savings
        if changed_files and selected_tests:
            total_tests = 100  # Placeholder
            time_saved_pct = (1 - len(selected_tests) / total_tests) * 100 if total_tests > 0 else 0
            print_success(f"\n💰 Time Savings: {time_saved_pct:.0f}%")
            print_info(f"  Running {len(selected_tests)}/{total_tests} tests")

    except Exception as e:
        print_error(f"Estimation failed: {e}")
        raise click.Abort()


if __name__ == '__main__':
    select()
