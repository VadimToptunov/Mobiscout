"""
Visual Testing CLI commands

Commands for visual regression testing.
"""

import shutil
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from framework.analysis.visual_analyzer import VisualAnalyzer
from framework.cli.rich_output import print_header, print_info, print_success, print_error

console = Console()


@click.group(name='visual')
def visual() -> None:
    """👁️  Visual regression testing commands"""
    pass


@visual.command()
@click.option('--baseline-dir', '-b', type=click.Path(), default='./visual_baselines',
              help='Baseline images directory')
@click.option('--current-dir', '-c', type=click.Path(exists=True), required=True,
              help='Current screenshots directory')
@click.option('--threshold', '-t', type=float, default=0.01,
              help='Difference threshold (0.01 = 1%)')
@click.option('--output', '-o', type=click.Path(), help='Output HTML report')
def compare(
        baseline_dir: str,
        current_dir: str,
        threshold: float,
        output: Optional[str]
) -> None:
    """Compare current screenshots against baselines"""
    print_header("Visual Regression Testing")

    baseline_path = Path(baseline_dir)
    current_path = Path(current_dir)

    if not baseline_path.exists():
        print_error(f"Baseline directory not found: {baseline_path}")
        print_info("\nCreate baselines first: observe visual capture --output ./visual_baselines")
        raise click.Abort()

    print_info(f"Baseline: {baseline_path}")
    print_info(f"Current: {current_path}")
    print_info(f"Threshold: {threshold * 100}%\n")

    # Initialize analyzer
    analyzer = VisualAnalyzer(baseline_dir=baseline_path)

    # Find all current screenshots
    current_screenshots = list(current_path.glob('*.png'))

    if not current_screenshots:
        print_error(f"No screenshots found in {current_path}")
        raise click.Abort()

    print_info(f"Found {len(current_screenshots)} screenshots\n")

    # Compare each screenshot
    regressions = []
    no_baseline = []
    passed = []

    for screenshot in current_screenshots:
        screen_name = screenshot.stem  # filename without extension

        diff = analyzer.compare_screenshots(
            screen_name=screen_name,
            current_image=screenshot,
            threshold=threshold
        )

        if diff is None:
            # No baseline exists
            no_baseline.append(screen_name)
            print_info(f"⚠️  {screen_name}: No baseline (created)")
        elif diff.has_regression:
            regressions.append(diff)
            print_error(f"❌ {screen_name}: Regression detected ({diff.diff_percentage:.2f}%)")
        else:
            passed.append(screen_name)
            print_success(f"✅ {screen_name}: Passed ({diff.diff_percentage:.2f}%)")

    # Summary
    print_info("\n" + "=" * 60)
    print_header("Summary")

    total = len(current_screenshots)
    passed_count = len(passed)
    failed_count = len(regressions)
    no_baseline_count = len(no_baseline)

    table = Table()
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right", style="cyan")
    table.add_column("Percentage", justify="right", style="yellow")

    table.add_row("✅ Passed", str(passed_count), f"{passed_count / total * 100:.1f}%")
    table.add_row("❌ Failed", str(failed_count), f"{failed_count / total * 100:.1f}%")
    table.add_row("⚠️  No Baseline", str(no_baseline_count), f"{no_baseline_count / total * 100:.1f}%")
    table.add_row("📊 Total", str(total), "100.0%")

    console.print(table)

    # Generate report if requested
    if output and analyzer.diffs:
        report_path = Path(output)
        analyzer.generate_html_report(report_path)
        print_success(f"\n📄 Report saved: {report_path}")

    # Exit code
    if failed_count > 0:
        print_error("\n❌ Visual regressions detected!")
        raise click.Abort()
    elif no_baseline_count > 0:
        print_info("\n⚠️  Some screens have no baseline")
    else:
        print_success("\n✅ All visual tests passed!")


@visual.command()
@click.option('--screenshots-dir', '-s', type=click.Path(exists=True), required=True,
              help='Directory containing screenshots')
@click.option('--output', '-o', type=click.Path(), default='./visual_baselines',
              help='Output directory for baselines')
def capture(screenshots_dir: str, output: str) -> None:
    """Capture baseline screenshots"""
    print_header("Capture Visual Baselines")

    screenshots_path = Path(screenshots_dir)
    output_path = Path(output)

    # Find all screenshots
    screenshots = list(screenshots_path.glob('*.png'))

    if not screenshots:
        print_error(f"No PNG screenshots found in {screenshots_path}")
        raise click.Abort()

    print_info(f"Found {len(screenshots)} screenshots")
    print_info(f"Output: {output_path}\n")

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    # Copy screenshots as baselines
    copied = 0
    for screenshot in screenshots:
        dest = output_path / screenshot.name
        shutil.copy2(screenshot, dest)
        print_success(f"✅ Captured: {screenshot.name}")
        copied += 1

    print_success(f"\n✅ Captured {copied} baseline screenshots")
    print_info(f"Baselines stored in: {output_path}")
    print_info("\nNext: observe visual compare --baseline-dir ./visual_baselines --current-dir ./screenshots")


@visual.command()
@click.argument('screen_name')
@click.option('--baseline-dir', '-b', type=click.Path(), default='./visual_baselines',
              help='Baseline images directory')
@click.option('--current-image', '-c', type=click.Path(exists=True), required=True,
              help='Current screenshot to approve')
def approve(screen_name: str, baseline_dir: str, current_image: str) -> None:
    """Approve current screenshot as new baseline"""
    print_header(f"Approve Visual Change: {screen_name}")

    baseline_path = Path(baseline_dir)
    current_path = Path(current_image)

    # Create baseline directory if it doesn't exist
    baseline_path.mkdir(parents=True, exist_ok=True)

    # Copy current as new baseline
    new_baseline = baseline_path / f"{screen_name}.png"

    if new_baseline.exists():
        print_info(f"⚠️  Overwriting existing baseline: {new_baseline}")

    shutil.copy2(current_path, new_baseline)

    print_success(f"✅ Approved: {screen_name}")
    print_info(f"New baseline: {new_baseline}")


@visual.command()
@click.option('--baseline-dir', '-b', type=click.Path(), default='./visual_baselines',
              help='Baseline images directory')
def list_baselines(baseline_dir: str) -> None:
    """List all baseline screenshots"""
    print_header("Visual Baselines")

    baseline_path = Path(baseline_dir)

    if not baseline_path.exists():
        print_info("No baselines directory found")
        print_info("\nCreate with: observe visual capture --screenshots-dir ./screenshots")
        return

    baselines = list(baseline_path.glob('*.png'))

    if not baselines:
        print_info(f"No baselines found in {baseline_path}")
        return

    print_info(f"Found {len(baselines)} baselines in {baseline_path}\n")

    table = Table()
    table.add_column("Screen", style="cyan")
    table.add_column("Size", justify="right", style="yellow")
    table.add_column("Modified", style="green")

    for baseline in sorted(baselines):
        size_kb = baseline.stat().st_size / 1024
        modified = baseline.stat().st_mtime

        from datetime import datetime
        modified_str = datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M')

        table.add_row(baseline.stem, f"{size_kb:.1f} KB", modified_str)

    console.print(table)


@visual.command()
@click.argument('screen_name')
@click.option('--baseline-dir', '-b', type=click.Path(), default='./visual_baselines',
              help='Baseline images directory')
@click.confirmation_option(prompt='Delete this baseline?')
def delete(screen_name: str, baseline_dir: str) -> None:
    """Delete a baseline screenshot"""
    print_header(f"Delete Baseline: {screen_name}")

    baseline_path = Path(baseline_dir) / f"{screen_name}.png"

    if not baseline_path.exists():
        print_error(f"Baseline not found: {baseline_path}")
        raise click.Abort()

    baseline_path.unlink()
    print_success(f"✅ Deleted: {screen_name}")


@visual.command()
@click.option('--baseline-dir', '-b', type=click.Path(), default='./visual_baselines',
              help='Baseline images directory')
@click.confirmation_option(prompt='Delete ALL baselines?')
def reset(baseline_dir: str) -> None:
    """Delete all baselines"""
    print_header("Reset Visual Baselines")

    baseline_path = Path(baseline_dir)

    if not baseline_path.exists():
        print_info("No baselines directory found")
        return

    baselines = list(baseline_path.glob('*.png'))

    if not baselines:
        print_info("No baselines to delete")
        return

    for baseline in baselines:
        baseline.unlink()

    print_success(f"✅ Deleted {len(baselines)} baselines")


@visual.command()
@click.option('--baseline-dir', '-b', type=click.Path(), default='./visual_baselines',
              help='Baseline images directory')
@click.option('--threshold', '-t', type=float, default=0.01,
              help='Difference threshold')
def config_info(baseline_dir: str, threshold: float) -> None:
    """Show visual testing configuration"""
    print_header("Visual Testing Configuration")

    baseline_path = Path(baseline_dir)

    print_info(f"Baseline directory: {baseline_path}")
    print_info(f"Threshold: {threshold * 100}%")

    if baseline_path.exists():
        baselines = list(baseline_path.glob('*.png'))
        print_info(f"Baselines count: {len(baselines)}")
        print_success("✅ Directory exists")
    else:
        print_info("Baselines count: 0")
        print_info("⚠️  Directory does not exist")

    print_info("\nWorkflow:")
    print_info("  1. observe visual capture --screenshots-dir ./screenshots")
    print_info("  2. observe visual compare --current-dir ./new_screenshots")
    print_info("  3. observe visual approve <screen> --current-image ./new_screenshots/screen.png")


if __name__ == '__main__':
    visual()
