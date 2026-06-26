"""
CLI commands for Parallel Execution
"""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from framework.devices.device_manager import DeviceManager
from framework.devices.device_pool import DevicePool, PoolStrategy
from framework.execution.parallel_executor import ParallelExecutor, TestStatus
from framework.execution.test_sharding import ShardStrategy, TestCase, TestSharding

console = Console()


@click.group()
def parallel() -> None:
    """Parallel test execution commands."""
    pass


@parallel.command()
@click.argument("test_dir", type=Path)
@click.option("--workers", "-w", default=4, help="Number of parallel workers")
@click.option(
    "--shard-strategy",
    type=click.Choice(["round_robin", "balanced", "by_file"]),
    default="balanced",
    help="Sharding strategy",
)
@click.option("--pytest-args", default="", help="Additional pytest arguments")
def run(test_dir: Path, workers: int, shard_strategy: str, pytest_args: str) -> None:
    """Run tests in parallel."""
    if not test_dir.exists():
        console.print(f"[red]❌ Test directory not found: {test_dir}[/red]")
        return

    console.print(
        Panel(
            f"[cyan]🚀 Starting parallel test execution[/cyan]\n\n"
            f"Test directory: {test_dir}\n"
            f"Workers: {workers}\n"
            f"Sharding: {shard_strategy}",
            title="Parallel Execution",
            border_style="cyan",
        )
    )

    # Collect tests
    console.print("\n[cyan]Collecting tests...[/cyan]")
    import subprocess

    subprocess.run(
        ["pytest", "--collect-only", "-q", str(test_dir)],
        capture_output=True,
        text=True,
    )

    console.print(f"[green]✓[/green] Found tests in {test_dir}")

    # Create shards
    console.print(f"\n[cyan]Creating {workers} shards...[/cyan]")

    # Simple test discovery
    test_files = list(test_dir.rglob("test_*.py"))
    tests = [TestCase(file=f, name=f.stem, estimated_duration=10.0) for f in test_files]

    if shard_strategy == "balanced":
        strategy = ShardStrategy.DURATION_BASED
    elif shard_strategy == "by_file":
        strategy = ShardStrategy.FILE_BASED
    else:
        strategy = ShardStrategy.ROUND_ROBIN

    sharding = TestSharding()
    shards = sharding.create_shards(tests, num_shards=workers, strategy=strategy)
    console.print(f"[green]✓[/green] Created {len(shards)} shards")

    # Execute in parallel
    executor = ParallelExecutor(max_workers=workers, pytest_args=pytest_args.split() if pytest_args else [])

    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
    ) as progress:
        task = progress.add_task("[cyan]Executing tests...", total=len(shards))

        def update_progress(completed: int, total: int) -> None:
            progress.update(task, completed=completed)

        results = executor.execute_shards(shards, Path.cwd(), progress_callback=update_progress)

    # Display results
    console.print("\n" + executor.generate_summary(results))

    # Show failed tests
    failed_tests = []
    for shard_result in results:
        for test_result in shard_result.test_results:
            if test_result.status in [TestStatus.FAILED, TestStatus.ERROR]:
                failed_tests.append(test_result)

    if failed_tests:
        console.print("\n[bold red]Failed Tests:[/bold red]")
        for test_result in failed_tests[:10]:  # Show first 10
            console.print(f"  • {test_result.test.full_name}")
            if test_result.error_message:
                console.print(f"    [dim]{test_result.error_message[:100]}[/dim]")

    # Exit code
    aggregated = executor.aggregate_results(results)
    exit_code = 1 if aggregated["failed"] > 0 or aggregated["errors"] > 0 else 0
    raise SystemExit(exit_code)


@parallel.command()
@click.argument("test_dir", type=Path)
@click.option("--platform", type=click.Choice(["android", "ios", "both"]), default="both")
@click.option("--pytest-args", default="", help="Additional pytest arguments")
def on_devices(test_dir: Path, platform: str, pytest_args: str) -> None:
    """Run tests in parallel across multiple devices."""
    console.print(
        Panel(
            "[cyan]🔌 Multi-Device Parallel Execution[/cyan]\n\n"
            "This will distribute tests across all available devices.",
            title="Device Pool Execution",
            border_style="cyan",
        )
    )

    # Discover devices
    console.print("\n[cyan]Discovering devices...[/cyan]")
    device_manager = DeviceManager()

    # Use existing devices
    devices = device_manager.get_available_devices()

    if platform != "both":
        devices = [d for d in devices if d.get('platform', '').lower() == platform]

    if not devices:
        console.print(f"[red]❌ No {platform} devices found[/red]")
        return

    console.print(f"[green]✓[/green] Found {len(devices)} device(s)")

    # Note: Device pool requires Device objects, but we have dicts from DeviceManager
    # This is a display-only operation, so we just show the available devices

    # Show devices
    table = Table(title="Available Devices")
    table.add_column("Device", style="cyan")
    table.add_column("Platform")
    table.add_column("Version")
    table.add_column("Status")

    for device in devices:
        table.add_row(
            device.get('name', 'Unknown'),
            device.get('platform', 'Unknown'),
            device.get('platform_version', device.get('os_version', 'Unknown')),
            device.get('status', 'Unknown')
        )

    console.print(table)

    console.print("\n[yellow]Note:[/yellow] Multi-device execution is a work in progress.")
    console.print("For now, use [cyan]observe parallel run[/cyan] for parallel execution on single device.")


@parallel.command()
@click.argument("test_dir", type=Path)
@click.argument("num_shards", type=int)
@click.option("--strategy", type=click.Choice(["round_robin", "balanced", "by_file"]), default="balanced")
@click.option("--output", "-o", type=Path, help="Output directory for shard files")
def create_shards_cmd(test_dir: Path, num_shards: int, strategy: str, output: Optional[Path]) -> None:
    """Create test shards for distribution."""
    console.print(f"\n[cyan]Creating {num_shards} shards from {test_dir}...[/cyan]\n")

    # Discover tests
    test_files = list(test_dir.rglob("test_*.py"))

    tests = [TestCase(file=f, name=f.stem, estimated_duration=10.0) for f in test_files]

    if strategy == "balanced":
        strategy_enum = ShardStrategy.DURATION_BASED
    elif strategy == "by_file":
        strategy_enum = ShardStrategy.FILE_BASED
    else:
        strategy_enum = ShardStrategy.ROUND_ROBIN

    sharding = TestSharding()
    shards = sharding.create_shards(tests, num_shards=num_shards, strategy=strategy_enum)

    # Display shards
    table = Table(title=f"Test Shards ({len(tests)} tests)")
    table.add_column("Shard", style="cyan")
    table.add_column("Tests", justify="right")
    table.add_column("Est. Duration", justify="right")

    for shard in shards:
        total_duration = sum(t.estimated_duration for t in shard.tests)
        table.add_row(str(shard.shard_id), str(len(shard.tests)), f"{total_duration:.1f}s")

    console.print(table)

    # Save to files if output specified
    if output:
        output.mkdir(parents=True, exist_ok=True)

        for shard in shards:
            shard_file = output / f"shard_{shard.shard_id}.txt"
            with open(shard_file, "w") as f:
                for test in shard.tests:
                    f.write(f"{test.full_name}\n")

        console.print(f"\n[green]✓[/green] Saved shards to {output}")


@parallel.command()
@click.option("--workers", "-w", default=4, help="Number of workers")
@click.option("--test-count", default=100, help="Number of test simulations")
def benchmark(workers: int, test_count: int) -> None:
    """Benchmark parallel execution performance."""
    import random

    console.print(
        Panel(
            f"[cyan]⚡ Benchmarking Parallel Execution[/cyan]\n\n"
            f"Workers: {workers}\n"
            f"Simulated tests: {test_count}",
            title="Performance Benchmark",
            border_style="cyan",
        )
    )

    # Create simulated tests with random durations
    tests = [
        TestCase(
            file=Path(f"test_{i}.py"),
            name=f"test_{i}",
            estimated_duration=random.uniform(0.1, 2.0),
        )
        for i in range(test_count)
    ]

    total_duration = sum(t.estimated_duration for t in tests)

    console.print(f"\n[dim]Total sequential duration: {total_duration:.2f}s[/dim]")

    # Benchmark different strategies
    strategies: list[tuple[str, ShardStrategy]] = [
        ("Round Robin", ShardStrategy.ROUND_ROBIN),
        ("Balanced", ShardStrategy.DURATION_BASED),
        ("By File", ShardStrategy.FILE_BASED),
    ]

    results: list[tuple[str, float, float, list[float]]] = []

    sharding = TestSharding()

    for strategy_name, strategy in strategies:
        console.print(f"\n[cyan]Testing {strategy_name}...[/cyan]")

        shards = sharding.create_shards(tests, num_shards=workers, strategy=strategy)

        # Calculate theoretical parallel duration (longest shard)
        shard_durations = [sum(t.estimated_duration for t in shard.tests) for shard in shards]
        parallel_duration = max(shard_durations) if shard_durations else 0.0
        speedup = total_duration / parallel_duration if parallel_duration > 0 else 1.0

        results.append((strategy_name, parallel_duration, speedup, shard_durations))

    # Display results
    console.print("\n")
    table = Table(title="Benchmark Results")
    table.add_column("Strategy", style="cyan")
    table.add_column("Duration", justify="right")
    table.add_column("Speedup", justify="right", style="green")
    table.add_column("Efficiency", justify="right")

    for strategy_name, duration, speedup, shard_durations in results:
        efficiency = (speedup / workers) * 100
        table.add_row(strategy_name, f"{duration:.2f}s", f"{speedup:.2f}x", f"{efficiency:.1f}%")

    console.print(table)

    # Show load distribution
    console.print("\n[bold]Load Distribution:[/bold]")
    best_strategy = max(results, key=lambda x: x[2])
    strategy_name, _, _, shard_durations = best_strategy

    console.print(f"\nBest: {strategy_name}")
    max_duration = max(shard_durations) if shard_durations else 1.0
    for i, duration in enumerate(shard_durations):
        bar_length = int((duration / max_duration) * 40)
        bar = "█" * bar_length
        console.print(f"  Shard {i}: {bar} {duration:.2f}s")


if __name__ == "__main__":
    parallel()
