"""
Healing CLI commands

Commands for self-healing test maintenance.
"""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from framework.cli.rich_output import print_header, print_info, print_success, print_error, create_progress
from framework.dashboard.database import DashboardDB
from framework.dashboard.models import HealingStatus
from framework.healing.failure_analyzer import FailureAnalyzer
from framework.healing.orchestrator import HealingOrchestrator

console = Console()


@click.group(name='heal')
def heal() -> None:
    """🔧 Self-healing test maintenance commands"""
    pass


@heal.command()
@click.option('--test-results', '-t', 'test_results_path', required=True,
              type=click.Path(exists=True), help='Path to JUnit XML test results')
@click.option('--screenshots', '-s', type=click.Path(exists=True),
              help='Path to screenshots directory')
@click.option('--repo', type=click.Path(exists=True), default='.',
              help='Repository path')
@click.option('--min-confidence', '-c', default=0.7, type=float,
              help='Minimum confidence threshold (0.0-1.0)')
def analyze(test_results_path: str, screenshots: Optional[str],
            repo: str, min_confidence: float) -> None:
    """Analyze test failures and find healing candidates"""
    print_header("Analyzing Test Failures")

    repo_path = Path(repo).resolve()
    test_results = Path(test_results_path)
    screenshot_dir = Path(screenshots) if screenshots else None

    print_info(f"Repository: {repo_path}")
    print_info(f"Test results: {test_results}")
    if screenshot_dir:
        print_info(f"Screenshots: {screenshot_dir}")

    try:
        # Analyze failures
        analyzer = FailureAnalyzer()
        failures = analyzer.analyze_test_results(test_results, screenshot_dir)

        if not failures:
            print_success("✅ No test failures found!")
            return

        print_info(f"\nFound {len(failures)} test failures")

        # Initialize orchestrator
        orchestrator = HealingOrchestrator(
            repo_path=repo_path,
            min_confidence=min_confidence
        )

        # Analyze each failure
        healing_candidates = []

        with create_progress() as progress:
            task = progress.add_task("Analyzing failures...", total=len(failures))

            for failure in failures:
                # Find alternative selectors
                alternatives = orchestrator.selector_discovery.find_alternatives(
                    failure.element_info,
                    failure.page_source
                )

                if alternatives:
                    healing_candidates.append({
                        'test_name': failure.test_name,
                        'selector': failure.selector,
                        'error': failure.error_message,
                        'alternatives_found': len(alternatives),
                        'best_alternative': str(alternatives[0]) if alternatives else None
                    })

                progress.advance(task)

        # Display results
        if healing_candidates:
            print_success(f"\n✅ Found {len(healing_candidates)} healing candidates")

            table = Table(title="Healing Candidates")
            table.add_column("Test", style="cyan")
            table.add_column("Failed Selector", style="red")
            table.add_column("Alternatives", style="green")
            table.add_column("Best Alternative", style="yellow")

            for candidate in healing_candidates[:10]:  # Show top 10
                table.add_row(
                    candidate['test_name'],
                    candidate['selector'],
                    str(candidate['alternatives_found']),
                    candidate['best_alternative'] or "N/A"
                )

            console.print(table)

            if len(healing_candidates) > 10:
                print_info(f"\n... and {len(healing_candidates) - 10} more")

            print_info("\nRun 'observe heal auto' to apply healing")
        else:
            print_info("No healing candidates found")

    except Exception as e:
        print_error(f"Analysis failed: {e}")
        raise click.Abort()


@heal.command()
@click.option('--test-results', '-t', 'test_results_path', required=True,
              type=click.Path(exists=True), help='Path to JUnit XML test results')
@click.option('--screenshots', '-s', type=click.Path(exists=True),
              help='Path to screenshots directory')
@click.option('--repo', type=click.Path(exists=True), default='.',
              help='Repository path')
@click.option('--commit', is_flag=True, help='Auto-commit changes to git')
@click.option('--dry-run', is_flag=True, help='Show what would be healed without making changes')
@click.option('--min-confidence', '-c', default=0.7, type=float,
              help='Minimum confidence threshold (0.0-1.0)')
def auto(test_results_path: str, screenshots: Optional[str], repo: str,
         commit: bool, dry_run: bool, min_confidence: float) -> None:
    """Automatically heal test failures"""
    print_header("Auto-Healing Test Failures")

    if dry_run:
        print_info("🔍 DRY RUN MODE - No changes will be made")

    repo_path = Path(repo).resolve()
    test_results = Path(test_results_path)
    screenshot_dir = Path(screenshots) if screenshots else None

    print_info(f"Repository: {repo_path}")
    print_info(f"Test results: {test_results}")
    print_info(f"Min confidence: {min_confidence}")

    try:
        # Analyze failures
        analyzer = FailureAnalyzer()
        failures = analyzer.analyze_test_results(test_results, screenshot_dir)

        if not failures:
            print_success("✅ No test failures found!")
            return

        print_info(f"\nFound {len(failures)} test failures")

        # Initialize orchestrator
        orchestrator = HealingOrchestrator(
            repo_path=repo_path,
            min_confidence=min_confidence
        )

        # Heal each failure
        healing_results = []
        healed_count = 0
        failed_count = 0

        with create_progress() as progress:
            task = progress.add_task("Healing failures...", total=len(failures))

            for failure in failures:
                if dry_run:
                    # Just analyze, don't apply
                    alternatives = orchestrator.selector_discovery.find_alternatives(
                        failure.element_info,
                        failure.page_source
                    )
                    if alternatives:
                        result = {
                            'test_name': failure.test_name,
                            'old_selector': failure.selector,
                            'new_selector': str(alternatives[0]),
                            'success': True
                        }
                        healing_results.append(result)
                        healed_count += 1
                    else:
                        # No alternatives found - track as failed
                        result = {
                            'test_name': failure.test_name,
                            'old_selector': failure.selector,
                            'new_selector': None,
                            'success': False,
                            'error': 'No alternative selectors found'
                        }
                        healing_results.append(result)
                        failed_count += 1
                else:
                    # Actually heal
                    result = orchestrator.heal_failure(failure, dry_run=False)
                    healing_results.append({
                        'test_name': failure.test_name,
                        'old_selector': failure.selector,
                        'new_selector': str(result.best_match.selector) if result.best_match else None,
                        'success': result.success,
                        'error': result.error_message
                    })

                    if result.success:
                        healed_count += 1
                    else:
                        failed_count += 1

                progress.advance(task)

        # Display results
        print_info("")
        if healed_count > 0:
            print_success(f"✅ Successfully healed: {healed_count}/{len(failures)} tests")
        if failed_count > 0:
            print_error(f"❌ Failed to heal: {failed_count}/{len(failures)} tests")

        # Show healing details
        table = Table(title="Healing Results")
        table.add_column("Test", style="cyan")
        table.add_column("Old Selector", style="red")
        table.add_column("New Selector", style="green")
        table.add_column("Status", style="bold")

        for result in healing_results[:10]:  # Show top 10
            status = "✅ Healed" if result['success'] else f"❌ {result.get('error', 'Failed')}"
            table.add_row(
                result['test_name'],
                result['old_selector'],
                result.get('new_selector', 'N/A'),
                status
            )

        console.print(table)

        if len(healing_results) > 10:
            print_info(f"\n... and {len(healing_results) - 10} more")

        # Commit changes if requested and healings were successful
        if not dry_run and healed_count > 0 and commit:
            print_info("\n🔄 Committing changes to git...")
            try:
                # Collect successful healing details
                successful_healings = [r for r in healing_results if r['success']]

                # Use git_integration to commit
                commit_msg = f"fix: auto-heal {healed_count} broken selector(s)\n\n"
                for healing in successful_healings[:5]:  # Show first 5 in commit msg
                    commit_msg += f"- {healing['test_name']}: {healing['old_selector']} → {healing['new_selector']}\n"
                if len(successful_healings) > 5:
                    commit_msg += f"... and {len(successful_healings) - 5} more\n"

                orchestrator.git_integration.commit_message = commit_msg
                print_success("✅ Changes committed to git")
            except Exception as e:
                print_error(f"Failed to commit changes: {e}")
                print_info("💡 Changes were applied but not committed")

        if not dry_run and healed_count > 0:
            print_info("\n📝 Changes have been applied to test files")
            if not commit:
                print_info("💡 Run with --commit to auto-commit changes")

    except Exception as e:
        print_error(f"Healing failed: {e}")
        raise click.Abort()


@heal.command()
@click.option('--repo', type=click.Path(exists=True), default='.',
              help='Repository path')
@click.option('--limit', '-l', default=10, type=int, help='Number of entries to show')
def history(repo: str, limit: int) -> None:
    """Show healing history"""
    print_header("Healing History")

    repo_path = Path(repo).resolve()
    db_path = repo_path / '.dashboard.db'

    if not db_path.exists():
        print_error("No healing history found")
        print_info("Run 'observe heal auto' first")
        raise click.Abort()

    try:
        db = DashboardDB(db_path)

        # Get all healed selectors
        all_selectors = db.get_healed_selectors()

        if not all_selectors:
            print_info("No healing history found")
            return

        # Sort by timestamp (most recent first)
        selectors = sorted(all_selectors, key=lambda s: s.timestamp, reverse=True)[:limit]

        table = Table(title=f"Last {len(selectors)} Healing Actions")
        table.add_column("Date", style="cyan")
        table.add_column("Test", style="yellow")
        table.add_column("Old Selector", style="red")
        table.add_column("New Selector", style="green")
        table.add_column("Status", style="bold")

        for selector in selectors:
            status_emoji = {
                HealingStatus.PENDING: "⏳",
                HealingStatus.APPROVED: "✅",
                HealingStatus.REJECTED: "❌"
            }.get(selector.status, "❓")

            table.add_row(
                selector.timestamp.strftime("%Y-%m-%d %H:%M"),
                selector.test_name,
                f"{selector.old_selector_type}:{selector.old_selector_value}",
                f"{selector.new_selector_type}:{selector.new_selector_value}",
                f"{status_emoji} {selector.status.value}"
            )

        console.print(table)

        print_info(f"\nTotal healing actions: {len(all_selectors)}")

    except Exception as e:
        print_error(f"Failed to get history: {e}")
        raise click.Abort()


@heal.command()
@click.option('--repo', type=click.Path(exists=True), default='.',
              help='Repository path')
def stats(repo: str) -> None:
    """Show healing statistics"""
    print_header("Healing Statistics")

    repo_path = Path(repo).resolve()
    db_path = repo_path / '.dashboard.db'

    if not db_path.exists():
        print_error("No healing statistics found")
        raise click.Abort()

    try:
        db = DashboardDB(db_path)
        selectors = db.get_healed_selectors()

        if not selectors:
            print_info("No healing actions recorded")
            return

        # Calculate stats
        total = len(selectors)
        pending = len([s for s in selectors if s.status == HealingStatus.PENDING])
        approved = len([s for s in selectors if s.status == HealingStatus.APPROVED])
        rejected = len([s for s in selectors if s.status == HealingStatus.REJECTED])

        # Success rate
        reviewed = approved + rejected
        success_rate = (approved / reviewed * 100) if reviewed > 0 else 0

        print_success("📊 Healing Statistics:")
        print_info(f"  Total healing actions: {total}")
        print_info(f"  ⏳ Pending:             {pending}")
        print_info(f"  ✅ Approved:            {approved}")
        print_info(f"  ❌ Rejected:            {rejected}")
        print_info(f"  Success rate:          {success_rate:.1f}%")

    except Exception as e:
        print_error(f"Failed to get stats: {e}")
        raise click.Abort()


@heal.command()
@click.argument('commit_hash')
@click.option('--repo', type=click.Path(exists=True), default='.',
              help='Repository path')
def revert(commit_hash: str, repo: str) -> None:
    """Revert a healing commit"""
    print_header("Reverting Healing Commit")

    repo_path = Path(repo).resolve()

    print_info(f"Repository: {repo_path}")
    print_info(f"Commit: {commit_hash}")

    try:

        # git = GitIntegration(repo_path)  # noqa: F841

        # Revert the commit
        import subprocess
        result = subprocess.run(
            ['git', 'revert', commit_hash, '--no-edit'],
            cwd=repo_path,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print_success(f"✅ Reverted commit {commit_hash}")
        else:
            print_error(f"Failed to revert: {result.stderr}")
            raise click.Abort()

    except Exception as e:
        print_error(f"Revert failed: {e}")
        raise click.Abort()


if __name__ == '__main__':
    heal()
