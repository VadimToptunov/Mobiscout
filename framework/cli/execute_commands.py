"""
Live Execution Monitor CLI

Real-time test execution monitoring with rich UI.
"""

import re
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from framework.cli.rich_output import print_header, print_info, print_success, print_error

console = Console()


class TestMonitor:
    """Monitor test execution in real-time"""

    def __init__(self) -> None:
        self.total_tests = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.current_test = "Initializing..."
        self.start_time = time.time()
        self.test_history: list[Dict[str, Any]] = []

    def update_progress(self, line: str) -> None:
        """Parse test output and update progress"""

        # Pytest output patterns
        if "PASSED" in line:
            self.passed += 1
            self._extract_test_name(line)
        elif "FAILED" in line:
            self.failed += 1
            self._extract_test_name(line)
        elif "SKIPPED" in line:
            self.skipped += 1
            self._extract_test_name(line)
        elif "test_" in line.lower():
            self._extract_test_name(line)

        # Track test history
        if len(self.test_history) > 10:
            self.test_history.pop(0)

    def _extract_test_name(self, line: str) -> None:
        """Extract test name from output"""
        # Try to find test name pattern
        match = re.search(r"test_\w+", line)
        if match:
            test_name = match.group(0)
            self.current_test = test_name
            self.test_history.append(
                {"name": test_name, "status": self._get_status_from_line(line), "time": time.time() - self.start_time}
            )

    def _get_status_from_line(self, line: str) -> str:
        """Determine test status from line"""
        if "PASSED" in line:
            return "✅ PASSED"
        elif "FAILED" in line:
            return "❌ FAILED"
        elif "SKIPPED" in line:
            return "⏭️  SKIPPED"
        return "🔄 RUNNING"

    def render_dashboard(self) -> Table:
        """Render live dashboard"""
        # Main stats table
        table = Table(title="🔴 LIVE Test Execution Monitor", style="bold")
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", justify="right", style="yellow", width=15)
        table.add_column("Bar", width=30)

        total = self.passed + self.failed + self.skipped
        elapsed = time.time() - self.start_time

        # Stats
        table.add_row("Total Tests", str(total), "")
        table.add_row("✅ Passed", str(self.passed), self._progress_bar(self.passed, total))
        table.add_row("❌ Failed", str(self.failed), self._progress_bar(self.failed, total, "red"))
        table.add_row("⏭️  Skipped", str(self.skipped), self._progress_bar(self.skipped, total, "yellow"))
        table.add_row("⏱️  Elapsed", f"{elapsed:.1f}s", "")
        table.add_row("🏃 Current", self.current_test[:30], "")

        return table

    def render_history(self) -> Panel:
        """Render recent test history"""
        if not self.test_history:
            return Panel("No tests executed yet", title="📋 Recent Tests")

        history_text = "\n".join(
            [f"{test['status']} {test['name']} ({test['time']:.1f}s)" for test in self.test_history[-5:]]
        )

        return Panel(history_text, title="📋 Recent Tests")

    def _progress_bar(self, value: int, total: int, color: str = "green") -> str:
        """Generate ASCII progress bar"""
        if total == 0:
            return ""

        percentage = value / total
        bar_length = 20
        filled = int(bar_length * percentage)
        bar = "█" * filled + "░" * (bar_length - filled)

        return f"[{color}]{bar}[/{color}] {percentage * 100:.0f}%"


def run_tests_with_monitor(test_path: str, pytest_args: str) -> int:
    """Run tests and monitor in real-time"""
    monitor = TestMonitor()

    # Build pytest command
    cmd = ["pytest", test_path, "-v"]
    if pytest_args:
        cmd.extend(pytest_args.split())

    print_info(f"Running: {' '.join(cmd)}\n")

    # Start process
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    # Live display
    with Live(monitor.render_dashboard(), console=console, refresh_per_second=4) as live:
        try:
            for line in process.stdout:  # type: ignore
                monitor.update_progress(line)

                # Update display
                dashboard = monitor.render_dashboard()
                live.update(dashboard)

        except KeyboardInterrupt:
            print_error("\n⚠️  Interrupted by user")
            process.terminate()
            return 130

    process.wait()

    # Final summary
    console.print("\n")
    console.print(monitor.render_dashboard())

    if monitor.test_history:
        console.print("\n")
        console.print(monitor.render_history())

    return process.returncode


@click.group(name="execute")
def execute() -> None:
    """🏃 Live test execution commands"""
    pass


@execute.command()
@click.argument("tests", type=click.Path(exists=True), default="tests/")
@click.option("--live", is_flag=True, help="Enable live monitoring")
@click.option("--args", "-a", help="Additional pytest arguments")
def run(tests: str, live: bool, args: Optional[str]) -> None:
    """Run tests with optional live monitoring"""
    print_header("Execute Tests")

    tests_path = Path(tests)
    print_info(f"Tests: {tests_path}")

    if live:
        print_info("Mode: Live monitoring\n")
        exit_code = run_tests_with_monitor(str(tests_path), args or "")
        raise SystemExit(exit_code)
    else:
        # Standard execution
        cmd = ["pytest", str(tests_path), "-v"]
        if args:
            cmd.extend(args.split())

        print_info(f"Running: {' '.join(cmd)}\n")
        result = subprocess.run(cmd)
        raise SystemExit(result.returncode)


@execute.command()
@click.argument("tests", type=click.Path(exists=True), default="tests/")
@click.option("--workers", "-w", type=int, default=4, help="Number of parallel workers")
@click.option("--args", "-a", help="Additional pytest arguments")
def parallel(tests: str, workers: int, args: Optional[str]) -> None:
    """Run tests in parallel"""
    print_header("Parallel Test Execution")

    tests_path = Path(tests)
    print_info(f"Tests: {tests_path}")
    print_info(f"Workers: {workers}\n")

    cmd = ["pytest", str(tests_path), "-v", "-n", str(workers)]
    if args:
        cmd.extend(args.split())

    print_info(f"Running: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd)
        raise SystemExit(result.returncode)
    except FileNotFoundError:
        print_error("pytest-xdist not installed")
        print_info("Install with: pip install pytest-xdist")
        raise click.Abort()


@execute.command()
@click.argument("tests", type=click.Path(exists=True), default="tests/")
@click.option("--duration", "-d", type=int, default=60, help="Duration in seconds")
@click.option("--args", "-a", help="Additional pytest arguments")
def stress(tests: str, duration: int, args: Optional[str]) -> None:
    """Stress test: run tests repeatedly"""
    print_header("Stress Testing")

    tests_path = Path(tests)
    print_info(f"Tests: {tests_path}")
    print_info(f"Duration: {duration}s\n")

    start_time = time.time()
    iterations = 0
    total_passed = 0
    total_failed = 0

    with console.status("[bold green]Running stress tests...") as status:
        while (time.time() - start_time) < duration:
            iterations += 1
            status.update(f"[bold green]Iteration {iterations}...")  # noqa: F541

            cmd = ["pytest", str(tests_path), "-q"]
            if args:
                cmd.extend(args.split())

            result = subprocess.run(cmd, capture_output=True, text=True)

            # Parse results
            if "passed" in result.stdout:
                match = re.search(r"(\d+) passed", result.stdout)
                if match:
                    total_passed += int(match.group(1))

            if "failed" in result.stdout:
                match = re.search(r"(\d+) failed", result.stdout)
                if match:
                    total_failed += int(match.group(1))

            time.sleep(1)  # Small delay between iterations

    # Summary
    elapsed = time.time() - start_time
    print_success("\n✅ Stress test complete")  # noqa: F541
    print_info(f"Iterations: {iterations}")
    print_info(f"Total passed: {total_passed}")
    print_info(f"Total failed: {total_failed}")  # noqa: F541
    print_info(f"Elapsed: {elapsed:.1f}s")


@execute.command()
@click.argument("tests", type=click.Path(exists=True), default="tests/")
@click.option("--interval", "-i", type=int, default=60, help="Check interval in seconds")
@click.option("--args", "-a", help="Additional pytest arguments")
def watch(tests: str, interval: int, args: Optional[str]) -> None:
    """Watch tests and re-run on changes"""
    print_header("Watch Mode")

    tests_path = Path(tests)
    print_info(f"Tests: {tests_path}")
    print_info(f"Interval: {interval}s")
    print_info("\nWatching for changes... (Ctrl+C to stop)\n")

    last_mtime: float = 0.0

    try:
        while True:
            # Check for file changes
            test_files = list(tests_path.rglob("*.py"))
            if not test_files:
                print_error("No Python test files found in directory")
                return

            current_mtime = max(f.stat().st_mtime for f in test_files if f.is_file())

            if current_mtime > last_mtime:
                last_mtime = current_mtime

                print_info("\n🔄 Changes detected, running tests...")
                print_info("=" * 60)

                cmd = ["pytest", str(tests_path), "-v"]
                if args:
                    cmd.extend(args.split())

                subprocess.run(cmd)

                print_info("=" * 60)
                print_info(f"Waiting for changes... (checking every {interval}s)\n")

            time.sleep(interval)

    except KeyboardInterrupt:
        print_info("\n⚠️  Watch mode stopped")


if __name__ == "__main__":
    execute()
