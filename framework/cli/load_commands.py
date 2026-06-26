"""
CLI Commands - Load testing and performance profiling
"""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from framework.testing.load_tester import (
    LoadTester,
    LoadTestConfig,
)
from framework.testing.profiler import (
    PerformanceProfiler,
    ProfilerConfig,
)

console = Console()


@click.group()
def load() -> None:
    """Load testing and performance profiling"""
    pass


@load.command()
@click.argument("test_path", type=click.Path(exists=True))
@click.option(
    "--profile",
    type=click.Choice(["smoke", "light", "medium", "heavy", "stress", "spike"]),
    default="light",
    help="Load profile to use"
)
@click.option("--users", type=int, help="Override number of virtual users")
@click.option("--duration", type=int, help="Override test duration (seconds)")
@click.option("--ramp-up", type=int, help="Override ramp-up time (seconds)")
@click.option("--output", type=click.Path(), help="Output directory for results")
@click.option("--fail-fast", is_flag=True, help="Stop on critical errors")
def run(
        test_path: str,
        profile: str,
        users: int | None,
        duration: int | None,
        ramp_up: int | None,
        output: str | None,
        fail_fast: bool,
) -> None:
    """Run load test"""
    console.print(Panel.fit("🔥 Load Testing", style="bold magenta"))

    # Get load profile
    load_profile = LoadTester.get_profile(profile)

    # Apply overrides
    if users:
        load_profile.virtual_users = users
    if duration:
        load_profile.duration_seconds = duration
    if ramp_up is not None:
        load_profile.ramp_up_seconds = ramp_up

    # Create config
    config = LoadTestConfig(
        test_path=Path(test_path),
        profile=load_profile,
        fail_fast=fail_fast,
        output_dir=Path(output) if output else None,
    )

    # Display config
    config_table = Table(title="Load Test Configuration")
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="green")

    config_table.add_row("Profile", load_profile.name)
    config_table.add_row("Virtual Users", str(load_profile.virtual_users))
    config_table.add_row("Duration", f"{load_profile.duration_seconds}s")
    config_table.add_row("Ramp-up", f"{load_profile.ramp_up_seconds}s")
    config_table.add_row("Test Path", test_path)

    console.print(config_table)
    console.print()

    # Run load test
    tester = LoadTester(config)

    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
    ) as progress:
        task = progress.add_task("Running load test...", total=None)

        def progress_callback(message: str) -> None:
            progress.update(task, description=message)

        result = tester.run(progress_callback=progress_callback)

    # Display results
    console.print()
    console.print(Panel.fit("📊 Load Test Results", style="bold green"))

    results_table = Table()
    results_table.add_column("Metric", style="cyan")
    results_table.add_column("Value", style="yellow")

    results_table.add_row("Duration", f"{result.duration_seconds:.2f}s")
    results_table.add_row("Total Tests", str(result.total_tests))
    results_table.add_row(
        "✅ Passed", f"{result.passed_tests} ({result.passed_tests / result.total_tests * 100:.1f}%)"
    )
    results_table.add_row(
        "❌ Failed", f"{result.failed_tests} ({result.failed_tests / result.total_tests * 100:.1f}%)"
    )
    results_table.add_row("Throughput", f"{result.throughput:.2f} tests/sec")
    results_table.add_row("Avg Response Time", f"{result.avg_response_time:.3f}s")
    results_table.add_row("Min Response Time", f"{result.min_response_time:.3f}s")
    results_table.add_row("Max Response Time", f"{result.max_response_time:.3f}s")
    results_table.add_row("P50 Response Time", f"{result.p50_response_time:.3f}s")
    results_table.add_row("P95 Response Time", f"{result.p95_response_time:.3f}s")
    results_table.add_row("P99 Response Time", f"{result.p99_response_time:.3f}s")

    console.print(results_table)

    # Display errors if any
    if result.errors:
        console.print()
        console.print(Panel.fit(f"⚠️ {len(result.errors)} Errors Detected", style="bold red"))

        errors_table = Table()
        errors_table.add_column("User", style="cyan")
        errors_table.add_column("Iteration", style="yellow")
        errors_table.add_column("Error", style="red")

        for error in result.errors[:10]:  # Show first 10 errors
            errors_table.add_row(
                str(error.get("user_id", "?")),
                str(error.get("iteration", "?")),
                error.get("error", "Unknown error"),
            )

        console.print(errors_table)

        if len(result.errors) > 10:
            console.print(f"... and {len(result.errors) - 10} more errors")

    # Save results
    if config.output_dir:
        output_file = config.output_dir / "load_test_results.json"
        tester.save_results(result, output_file)
        console.print(f"\n💾 Results saved to: {output_file}")


@load.command()
def profiles() -> None:
    """List available load profiles"""
    console.print(Panel.fit("📋 Available Load Profiles", style="bold cyan"))

    table = Table()
    table.add_column("Name", style="cyan")
    table.add_column("Users", style="yellow")
    table.add_column("Duration", style="green")
    table.add_column("Ramp-up", style="magenta")
    table.add_column("Description", style="white")

    for profile in LoadTester.list_profiles():
        table.add_row(
            profile.name,
            str(profile.virtual_users),
            f"{profile.duration_seconds}s",
            f"{profile.ramp_up_seconds}s",
            profile.description,
        )

    console.print(table)


@load.command()
@click.argument("test_path", type=click.Path(exists=True))
@click.option("--cpu/--no-cpu", default=True, help="Profile CPU usage")
@click.option("--memory/--no-memory", default=True, help="Profile memory usage")
@click.option("--top", type=int, default=20, help="Number of top functions to show")
@click.option("--output", type=click.Path(), help="Output path for profile data")
@click.option("--report", type=click.Path(), help="Generate HTML report")
def profile(
        test_path: str,
        cpu: bool,
        memory: bool,
        top: int,
        output: str | None,
        report: str | None,
) -> None:
    """Profile test performance"""
    console.print(Panel.fit("🔬 Performance Profiling", style="bold cyan"))

    # Create profiler config
    config = ProfilerConfig(
        profile_cpu=cpu,
        profile_memory=memory,
        top_functions=top,
    )

    profiler = PerformanceProfiler(config)

    # Run profiling
    console.print(f"Profiling: {test_path}")
    console.print(f"CPU: {'✅' if cpu else '❌'} | Memory: {'✅' if memory else '❌'}")
    console.print()

    def test_function() -> None:
        """Dummy test function - replace with actual test execution"""
        import time
        time.sleep(0.1)  # Simulate test execution

    with console.status("[bold green]Running profiler..."):
        result = profiler.profile_test(
            Path(test_path),
            test_function,
        )

    # Display results
    console.print(Panel.fit("📊 Profile Results", style="bold green"))

    metrics_table = Table()
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", style="yellow")

    metrics_table.add_row("Duration", f"{result.duration_seconds:.3f}s")

    if result.memory_profile:
        total_mb = result.memory_profile.get("total_size_mb", 0)
        num_allocs = result.memory_profile.get("num_allocations", 0)
        metrics_table.add_row("Memory Usage", f"{total_mb:.2f} MB")
        metrics_table.add_row("Allocations", f"{num_allocs:,}")

    console.print(metrics_table)

    # CPU Profile
    if result.cpu_profile:
        console.print()
        console.print(Panel.fit("🔥 CPU Profile - Top Functions", style="bold yellow"))

        cpu_table = Table()
        cpu_table.add_column("Function", style="cyan")
        cpu_table.add_column("Calls", style="yellow")
        cpu_table.add_column("Total Time", style="green")
        cpu_table.add_column("Time/Call", style="magenta")

        for func in result.cpu_profile.get("top_functions", [])[:10]:
            cpu_table.add_row(
                func["function"][:50],
                f"{func['calls']:,}",
                f"{func['total_time']:.4f}s",
                f"{func['time_per_call']:.6f}s",
            )

        console.print(cpu_table)

    # Memory Profile
    if result.memory_profile:
        console.print()
        console.print(Panel.fit("💾 Memory Profile - Top Allocations", style="bold blue"))

        mem_table = Table()
        mem_table.add_column("Location", style="cyan")
        mem_table.add_column("Size (MB)", style="yellow")
        mem_table.add_column("Count", style="green")

        for alloc in result.memory_profile.get("top_allocations", [])[:10]:
            mem_table.add_row(
                alloc["filename"][:60],
                f"{alloc['size_mb']:.2f}",
                f"{alloc['count']:,}",
            )

        console.print(mem_table)

    # Save results
    if output:
        output_path = Path(output)
        profiler.save_profile(result, output_path)
        console.print(f"\n💾 Profile saved to: {output_path}")

    if report:
        report_path = Path(report)
        profiler.generate_report(result, report_path)
        console.print(f"📄 HTML report saved to: {report_path}")


@load.command()
@click.argument("baseline", type=click.Path(exists=True))
@click.argument("current", type=click.Path(exists=True))
def compare(baseline: str, current: str) -> None:
    """Compare two profile results"""
    import json

    console.print(Panel.fit("🔄 Profile Comparison", style="bold cyan"))

    # Load profiles
    with open(baseline) as f:
        baseline_data = json.load(f)

    with open(current) as f:
        current_data = json.load(f)

    console.print(f"Baseline: {baseline}")
    console.print(f"Current:  {current}")
    console.print()

    # Compare durations
    baseline_duration = baseline_data.get("duration_seconds", 0)
    current_duration = current_data.get("duration_seconds", 0)
    duration_diff = current_duration - baseline_duration
    duration_pct = (duration_diff / baseline_duration * 100) if baseline_duration > 0 else 0

    table = Table(title="Performance Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Baseline", style="yellow")
    table.add_column("Current", style="yellow")
    table.add_column("Change", style="green" if duration_diff <= 0 else "red")

    table.add_row(
        "Duration",
        f"{baseline_duration:.3f}s",
        f"{current_duration:.3f}s",
        f"{duration_diff:+.3f}s ({duration_pct:+.1f}%)",
    )

    # Compare memory if available
    if "memory_profile" in baseline_data and "memory_profile" in current_data:
        baseline_mem = baseline_data["memory_profile"].get("total_size_mb", 0)
        current_mem = current_data["memory_profile"].get("total_size_mb", 0)
        mem_diff = current_mem - baseline_mem
        mem_pct = (mem_diff / baseline_mem * 100) if baseline_mem > 0 else 0

        table.add_row(
            "Memory",
            f"{baseline_mem:.2f} MB",
            f"{current_mem:.2f} MB",
            f"{mem_diff:+.2f} MB ({mem_pct:+.1f}%)",
        )

    console.print(table)

    # Verdict
    if duration_diff > 0:
        console.print("\n⚠️ [red]Performance regression detected![/red]")
    elif duration_diff < 0:
        console.print("\n✅ [green]Performance improvement detected![/green]")
    else:
        console.print("\n➡️ [yellow]No significant change in performance.[/yellow]")
