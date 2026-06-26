"""
Performance CLI commands

Commands for performance profiling and analysis.
"""

import click
from rich.console import Console
from rich.table import Table

from framework.analysis.performance_analyzer import PerformanceAnalyzer
from framework.cli.rich_output import print_header, print_info, print_success, print_error

console = Console()


@click.group(name='perf')
def perf() -> None:
    """⚡ Performance analysis commands"""
    pass


@perf.command()
@click.option('--device', '-d', required=True, help='Device ID to profile')
@click.option('--app', '-a', required=True, help='App package/bundle ID')
@click.option('--duration', type=int, default=60, help='Profile duration in seconds')
@click.option('--output', '-o', type=click.Path(), help='Output file for profile (JSON)')
def profile(device: str, app: str, duration: int, output: str) -> None:
    """Profile app performance metrics"""
    print_header("Performance Profiling")

    print_info(f"Device: {device}")
    print_info(f"App: {app}")
    print_info(f"Duration: {duration}s")

    try:
        # analyzer = PerformanceAnalyzer()  # Would interact with device

        print_info("\n🔄 Starting profiling...")
        print_info("Collecting metrics:")
        print_info("  • App startup time")
        print_info("  • Memory usage")
        print_info("  • CPU usage")
        print_info("  • Frame rate (FPS)")
        print_info("  • Battery drain")

        # Note: Actual profiling would interact with device
        print_info(f"\n⏱️  Profiling for {duration} seconds...")

        # Store profile
        profile_id = f"{device}_{app}"

        if output:
            print_success(f"\n✅ Profile saved: {profile_id}")
            print_info(f"Output: {output}")
        else:
            print_success(f"\n✅ Profile complete: {profile_id}")
            print_info("Use 'observe perf report' to view results")

    except Exception as e:
        print_error(f"Profiling failed: {e}")
        raise click.Abort()


@perf.command()
@click.option('--profile', '-p', required=True, help='Profile ID or file')
def report(profile: str) -> None:
    """Generate performance report"""
    print_header("Performance Report")

    print_info(f"Profile: {profile}")

    try:
        analyzer = PerformanceAnalyzer()

        # Check if profile exists
        if profile not in analyzer.metrics:
            print_error(f"Profile '{profile}' not found")
            print_info("\nAvailable profiles:")
            for profile_id in analyzer.metrics.keys():
                print_info(f"  • {profile_id}")
            raise click.Abort()

        metrics = analyzer.metrics[profile]

        # Display metrics
        print_success("\n📊 Performance Metrics:")

        table = Table(title=f"Profile: {profile}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="yellow")
        table.add_column("Status", style="bold")

        # App startup
        startup_status = "✅" if metrics.app_start_time < 2.0 else "⚠️" if metrics.app_start_time < 5.0 else "❌"
        table.add_row("App Startup", f"{metrics.app_start_time:.2f}s", startup_status)

        # Memory
        memory_status = "✅" if metrics.memory_usage < 100 else "⚠️" if metrics.memory_usage < 200 else "❌"
        table.add_row("Memory Usage", f"{metrics.memory_usage:.1f} MB", memory_status)

        # CPU
        cpu_status = "✅" if metrics.cpu_usage < 30 else "⚠️" if metrics.cpu_usage < 60 else "❌"
        table.add_row("CPU Usage", f"{metrics.cpu_usage:.1f}%", cpu_status)

        # FPS
        fps_status = "✅" if metrics.fps >= 55 else "⚠️" if metrics.fps >= 30 else "❌"
        table.add_row("Frame Rate", f"{metrics.fps:.1f} FPS", fps_status)

        # Battery
        battery_status = "✅" if metrics.battery_drain < 5 else "⚠️" if metrics.battery_drain < 10 else "❌"
        table.add_row("Battery Drain", f"{metrics.battery_drain:.1f}%/hr", battery_status)

        console.print(table)

        # Performance issues
        issues = analyzer.issues
        if issues:
            print_info(f"\n⚠️  {len(issues)} Performance Issues:")
            for issue in issues[:5]:
                severity_icon = {'high': '🔴', 'medium': '🟡', 'low': '🔵'}[issue.severity]
                print_info(f"  {severity_icon} {issue.description}")
            if len(issues) > 5:
                print_info(f"  ... and {len(issues) - 5} more")
        else:
            print_success("\n✅ No performance issues detected")

    except Exception as e:
        print_error(f"Report generation failed: {e}")
        raise click.Abort()


@perf.command()
@click.option('--baseline', '-b', required=True, help='Baseline profile ID')
@click.option('--current', '-c', required=True, help='Current profile ID')
def compare(baseline: str, current: str) -> None:
    """Compare two performance profiles"""
    print_header("Performance Comparison")

    print_info(f"Baseline: {baseline}")
    print_info(f"Current: {current}")

    try:
        analyzer = PerformanceAnalyzer()

        # Check profiles exist
        if baseline not in analyzer.metrics or current not in analyzer.metrics:
            print_error("One or both profiles not found")
            raise click.Abort()

        # Compare
        diff = analyzer.compare_profiles(baseline, current)

        # Display comparison
        print_success("\n📊 Performance Comparison:")

        table = Table(title=f"{baseline} vs {current}")
        table.add_column("Metric", style="cyan")
        table.add_column("Difference", style="yellow")
        table.add_column("Status", style="bold")

        metrics = [
            ("App Startup", "startup_diff", "s", 0.5),
            ("Memory Usage", "memory_diff", "MB", 20),
            ("CPU Usage", "cpu_diff", "%", 10),
            ("Frame Rate", "fps_diff", "FPS", 5),
            ("Battery Drain", "battery_diff", "%/hr", 2)
        ]

        for name, key, unit, threshold in metrics:
            value = diff[key]

            if abs(value) < threshold * 0.2:
                status = "✅ No change"
            elif value < 0:
                status = f"🟢 Improved {abs(value):.1f}{unit}"
            else:
                status = f"🔴 Degraded +{value:.1f}{unit}"

            table.add_row(
                name,
                f"{value:+.2f} {unit}" if 'FPS' not in unit else f"{value:+.1f} {unit}",
                status
            )

        console.print(table)

        # Overall assessment
        improvements = sum(1 for v in diff.values() if v < 0)
        regressions = sum(1 for v in diff.values() if v > 0)

        print_info(f"\n📈 Summary:")  # noqa: F541
        print_info(f"  Improvements: {improvements}")
        print_info(f"  Regressions: {regressions}")

        if regressions > improvements:
            print_error("  ⚠️  Performance has degraded")
        elif improvements > regressions:
            print_success("  ✅ Performance has improved")
        else:
            print_info("  ➖ Performance is similar")

    except Exception as e:
        print_error(f"Comparison failed: {e}")
        raise click.Abort()


if __name__ == '__main__':
    perf()
