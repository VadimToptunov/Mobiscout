"""
Dashboard CLI commands

Commands for running and managing the test maintenance dashboard.
"""

import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import click

from framework.cli.rich_output import print_header, print_info, print_success, print_error
from framework.dashboard.database import DashboardDB
from framework.dashboard.server import DashboardServer
from framework.reporting.junit_parser import JUnitParser


@click.group(name='dashboard')
def dashboard() -> None:
    """🎯 Test maintenance dashboard commands"""
    pass


@dashboard.command()
@click.option('--port', '-p', default=8080, help='Server port')
@click.option('--host', '-h', default='localhost', help='Server host')
@click.option('--no-browser', is_flag=True, help='Don\'t open browser automatically')
@click.option('--repo', type=click.Path(exists=True), default='.', help='Repository path')
def start(port: int, host: str, no_browser: bool, repo: str) -> None:
    """Start the dashboard web server"""
    print_header("Starting Dashboard Server")

    repo_path = Path(repo).resolve()
    print_info(f"Repository: {repo_path}")
    print_info(f"Server: http://{host}:{port}")

    try:
        server = DashboardServer(repo_path=repo_path)

        # Open browser after a short delay
        if not no_browser:
            def open_browser():
                time.sleep(1.5)
                url = f"http://{host}:{port}"
                print_info(f"Opening browser: {url}")
                webbrowser.open(url)

            threading.Thread(target=open_browser, daemon=True).start()

        print_success("Dashboard server started!")
        print_info("Press Ctrl+C to stop")
        print_info("")

        # Run server
        server.run(host=host, port=port)

    except KeyboardInterrupt:
        print_info("\nShutting down...")
    except Exception as e:
        print_error(f"Failed to start dashboard: {e}")
        raise click.Abort()


@dashboard.command()
@click.option('--junit-xml', '-j', 'junit_path', required=True, type=click.Path(exists=True),
              help='Path to JUnit XML file')
@click.option('--repo', type=click.Path(exists=True), default='.', help='Repository path')
def import_results(junit_path: str, repo: str) -> None:
    """Import test results from JUnit XML"""
    print_header("Importing Test Results")

    junit_file = Path(junit_path)
    repo_path = Path(repo).resolve()
    db_path = repo_path / '.dashboard.db'

    print_info(f"JUnit file: {junit_file}")
    print_info(f"Database: {db_path}")

    try:
        # Parse JUnit XML
        parser = JUnitParser()
        results = parser.parse(junit_file)

        print_info(f"Found {len(results.tests)} test results")

        # Import into database
        db = DashboardDB(db_path)

        imported = 0
        for result in results.tests:
            db.add_test_result(result)
            imported += 1

        print_success(f"✅ Imported {imported} test results")
        print_info("View results: observe dashboard start")

    except Exception as e:
        print_error(f"Failed to import results: {e}")
        raise click.Abort()


@dashboard.command()
@click.option('--repo', type=click.Path(exists=True), default='.', help='Repository path')
@click.option('--days', '-d', default=30, help='Number of days to analyze')
def stats(repo: str, days: int) -> None:
    """Show dashboard statistics"""
    print_header("Dashboard Statistics")

    repo_path = Path(repo).resolve()
    db_path = repo_path / '.dashboard.db'

    if not db_path.exists():
        print_error("No dashboard database found. Import test results first:")
        print_info("  observe dashboard import-results --junit-xml results.xml")
        raise click.Abort()

    try:
        db = DashboardDB(db_path)

        # Get test health
        health = db.get_test_health(days=days)

        if not health:
            print_info(f"No test data found for the last {days} days")
            return

        total_tests = len(health)
        passing = len([h for h in health if h.pass_rate >= 0.8])
        failing = len([h for h in health if h.pass_rate < 0.5])
        flaky = len([h for h in health if h.is_flaky])

        avg_pass_rate = sum(h.pass_rate for h in health) / total_tests if total_tests > 0 else 0.0

        # Get healing stats
        from framework.dashboard.models import HealingStatus
        pending_selectors = len(db.get_healed_selectors(HealingStatus.PENDING))
        approved_selectors = len(db.get_healed_selectors(HealingStatus.APPROVED))

        # Display stats
        print_info(f"Period: Last {days} days")
        print_info("")
        print_success("📊 Test Statistics:")
        print_info(f"  Total tests:    {total_tests}")
        print_info(f"  ✅ Passing:      {passing} ({passing / total_tests * 100:.1f}%)")
        print_info(f"  ❌ Failing:      {failing} ({failing / total_tests * 100:.1f}%)")
        print_info(f"  ⚠️  Flaky:        {flaky} ({flaky / total_tests * 100:.1f}%)")
        print_info(f"  Avg pass rate:  {avg_pass_rate * 100:.1f}%")
        print_info("")
        print_success("🔧 Healing Statistics:")
        print_info(f"  Pending:        {pending_selectors}")
        print_info(f"  Approved:       {approved_selectors}")

    except Exception as e:
        print_error(f"Failed to get stats: {e}")
        raise click.Abort()


@dashboard.command()
@click.option('--repo', type=click.Path(exists=True), default='.', help='Repository path')
@click.option('--format', '-f', type=click.Choice(['json', 'prometheus']), default='json',
              help='Export format')
@click.option('--output', '-o', type=click.Path(), help='Output file (default: stdout)')
def export(repo: str, format: str, output: Optional[str]) -> None:
    """Export metrics for external monitoring"""
    print_header(f"Exporting Metrics ({format})")

    repo_path = Path(repo).resolve()
    db_path = repo_path / '.dashboard.db'

    if not db_path.exists():
        print_error("No dashboard database found")
        raise click.Abort()

    try:
        db = DashboardDB(db_path)
        health = db.get_test_health(days=30)

        if format == 'json':
            import json
            metrics = {
                'total_tests': len(health),
                'passing_tests': len([h for h in health if h.pass_rate >= 0.8]),
                'failing_tests': len([h for h in health if h.pass_rate < 0.5]),
                'flaky_tests': len([h for h in health if h.is_flaky]),
                'avg_pass_rate': sum(h.pass_rate for h in health) / len(health) if health else 0.0
            }
            content = json.dumps(metrics, indent=2)

        elif format == 'prometheus':
            total = len(health)
            passing = len([h for h in health if h.pass_rate >= 0.8])
            failing = len([h for h in health if h.pass_rate < 0.5])
            flaky = len([h for h in health if h.is_flaky])
            avg_pass_rate = sum(h.pass_rate for h in health) / total if total > 0 else 0.0

            content = f"""# HELP test_total Total number of tests
# TYPE test_total gauge
test_total {total}

# HELP test_passing Number of passing tests
# TYPE test_passing gauge
test_passing {passing}

# HELP test_failing Number of failing tests
# TYPE test_failing gauge
test_failing {failing}

# HELP test_flaky Number of flaky tests
# TYPE test_flaky gauge
test_flaky {flaky}

# HELP test_pass_rate Average pass rate
# TYPE test_pass_rate gauge
test_pass_rate {avg_pass_rate}
"""
        else:
            content = ""

        if output:
            Path(output).write_text(content)
            print_success(f"✅ Exported to: {output}")
        else:
            print(content)

    except Exception as e:
        print_error(f"Failed to export metrics: {e}")
        raise click.Abort()


if __name__ == '__main__':
    dashboard()
