"""
CLI commands for self-learning ML system.
"""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.table import Table

from framework.config import ConfigManager
from framework.ml.self_learning import SelfLearningCollector, ModelUpdater, FeedbackCollector

console = Console()


# Individual command functions (not a group)
@click.command()
def check_updates():
    """Check for ML model updates."""
    console.print("\n🔍 Checking for model updates...", style="cyan")

    try:
        updater = ModelUpdater()
        update = updater.check_for_updates()

        if update:
            console.print(
                Panel(
                    f"[green]✅ New model available![/green]\n\n"
                    f"Current version: {updater._get_current_version()}\n"
                    f"Latest version: {update['version']}\n"
                    f"Release date: {update['release_date']}\n"
                    f"Size: {update['size_mb']} MB\n\n"
                    f"[bold]Improvements:[/bold]\n{update['changelog']}\n\n"
                    f"Run [cyan]observe ml update-model[/cyan] to install",
                    title="Model Update Available",
                    border_style="green",
                )
            )
        else:
            console.print("✅ Your model is up to date!", style="green")

    except Exception as e:
        console.print(f"❌ Error checking updates: {e}", style="red")


@click.command()
@click.option("--auto", is_flag=True, help="Check and install automatically")
def update_model(auto: bool):
    """Update ML model to latest version."""
    updater = ModelUpdater()

    if auto:
        console.print("\n🔄 Auto-updating model...", style="cyan")
        if updater.auto_update():
            console.print("✅ Model updated successfully!", style="green")
        else:
            console.print("ℹ️  Model is already up to date", style="blue")
        return

    # Manual update
    update = updater.check_for_updates()

    if not update:
        console.print("✅ Your model is already up to date!", style="green")
        return

    # Confirm with user
    if not click.confirm(f"\nUpdate to version {update['version']}?"):
        console.print("Update cancelled", style="yellow")
        return

    console.print(f"\n📥 Downloading model v{update['version']}...", style="cyan")

    if updater.download_update(update):
        console.print(
            Panel(
                f"[green]✅ Model updated successfully![/green]\n\n"
                f"Version: {update['version']}\n"
                f"Accuracy: {update.get('accuracy', 'N/A')}\n\n"
                f"[dim]Location: ml_models/universal_element_classifier.pkl[/dim]",
                title="Update Complete",
                border_style="green",
            )
        )
    else:
        console.print("❌ Update failed", style="red")


@click.command()
def stats():
    """Show ML contribution statistics."""
    collector = SelfLearningCollector(opt_in=True)

    total_samples = collector.get_local_samples_count()

    # Load batch files for detailed stats
    batch_files = list(collector.local_cache_dir.glob("batch_*.json"))

    platform_counts = {}
    element_type_counts = {}

    import json

    for batch_file in batch_files:
        with open(batch_file, "r") as f:
            batch = json.load(f)

            # Platform distribution
            for platform, count in batch.get("platform_distribution", {}).items():
                platform_counts[platform] = platform_counts.get(platform, 0) + count

            # Element type distribution
            for sample in batch.get("samples", []):
                elem_type = sample.get("element_type", "unknown")
                element_type_counts[elem_type] = element_type_counts.get(elem_type, 0) + 1

    # Create table
    table = Table(title="Your ML Contributions", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Total Samples", str(total_samples))
    table.add_row("Batches Collected", str(len(batch_files)))
    table.add_row("Cache Directory", str(collector.local_cache_dir))

    console.print("\n")
    console.print(table)

    # Platform distribution
    if platform_counts:
        console.print("\n[bold]Platform Distribution:[/bold]")
        for platform, count in sorted(platform_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_samples * 100) if total_samples > 0 else 0
            console.print(f"  • {platform}: {count} ({percentage:.1f}%)")

    # Element types
    if element_type_counts:
        console.print("\n[bold]Top Element Types:[/bold]")
        top_types = sorted(element_type_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for elem_type, count in top_types:
            console.print(f"  • {elem_type}: {count}")

    # Contribution message
    if total_samples > 0:
        console.print(
            Panel(
                f"[green]Thank you for contributing {total_samples} samples! 🎉[/green]\n\n"
                "Your data helps improve the ML model for everyone.\n"
                "Together we're building the best mobile testing tool!",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                "[yellow]No contributions yet[/yellow]\n\n"
                "Use the framework to analyze apps, and training data will be\n"
                "collected automatically (if enabled).\n\n"
                "To enable: [cyan]observe config set ml.contribute true[/cyan]",
                border_style="yellow",
            )
        )


@click.command()
@click.option("--enable/--disable", default=True, help="Enable or disable data collection")
def contribute(enable: bool):
    """Enable or disable ML data contribution."""
    if enable:
        console.print(
            Panel(
                "[bold]ML Data Contribution[/bold]\n\n"
                "[green]You are enabling automatic data collection.[/green]\n\n"
                "[bold]What is collected:[/bold]\n"
                "• Element attributes (class, clickable, focusable, etc.)\n"
                "• Bounds (width, height)\n"
                "• Platform (android, ios, flutter, react-native)\n\n"
                "[bold]What is NOT collected:[/bold]\n"
                "❌ App names or package IDs\n"
                "❌ Actual text content (only length)\n"
                "❌ Screenshots\n"
                "❌ User data or identifiers\n"
                "❌ API calls\n\n"
                "[dim]Data is anonymized and helps improve the model for everyone.[/dim]\n"
                "[dim]You can disable this at any time with:[/dim]\n"
                "[cyan]observe ml contribute --disable[/cyan]",
                title="Privacy Notice",
                border_style="cyan",
            )
        )

        if not click.confirm("\nDo you agree to contribute anonymized data?"):
            console.print("Contribution not enabled", style="yellow")
            return

        # Enable contribution in config
        config_manager = ConfigManager()
        config_manager.set("ml.contribute", True)

        collector = SelfLearningCollector()
        console.print("✅ ML contribution enabled! Thank you! 🎉", style="green")
        console.print(f"[dim]Data will be collected to {collector.local_cache_dir}[/dim]")

    else:
        # Disable contribution
        config_manager = ConfigManager()
        config_manager.set("ml.contribute", False)
        console.print("✅ ML contribution disabled", style="green")
        console.print("[dim]Existing cached data will not be deleted[/dim]")


@click.command()
@click.option("--output", "-o", type=Path, help="Output directory")
def export_cache(output: Path):
    """Export cached training data."""
    if not output:
        output = Path("ml_exports")

    collector = SelfLearningCollector()
    batch_files = list(collector.local_cache_dir.glob("batch_*.json"))

    if not batch_files:
        console.print("No cached data to export", style="yellow")
        return

    output.mkdir(parents=True, exist_ok=True)

    import shutil

    for batch_file in track(batch_files, description="Exporting batches..."):
        shutil.copy(batch_file, output / batch_file.name)

    console.print(f"\n✅ Exported {len(batch_files)} batches to {output}", style="green")


@click.command()
@click.confirmation_option(prompt="Are you sure you want to clear all cached data?")
def clear_cache():
    """Clear local training data cache."""
    collector = SelfLearningCollector()
    batch_files = list(collector.local_cache_dir.glob("batch_*.json"))

    if not batch_files:
        console.print("Cache is already empty", style="yellow")
        return

    for batch_file in track(batch_files, description="Clearing cache..."):
        batch_file.unlink()

    console.print(f"\n✅ Cleared {len(batch_files)} cached batches", style="green")


@click.command()
@click.argument("element_id")
@click.option("--predicted", required=True, help="What ML predicted")
@click.option("--actual", required=True, help="What it actually is")
@click.option("--platform", required=True, type=click.Choice(["android", "ios", "flutter", "react-native"]))
def correct(element_id: str, predicted: str, actual: str, platform: str):
    """Record a correction for ML misclassification."""
    feedback = FeedbackCollector()

    # In real usage, element would come from context
    # For now, create minimal element dict
    element = {
        "id": element_id,
        "class": "unknown",  # Would be filled from actual element
    }

    feedback.record_correction(element=element, predicted_type=predicted, actual_type=actual, platform=platform)

    console.print(
        Panel(
            f"[green]✅ Correction recorded![/green]\n\n"
            f"Predicted: {predicted}\n"
            f"Actual: {actual}\n"
            f"Platform: {platform}\n\n"
            f"[dim]This will help improve the model in the next update.[/dim]",
            title="Feedback Submitted",
            border_style="green",
        )
    )


@click.command()
def info():
    """Show ML system information."""
    updater = ModelUpdater()
    collector = SelfLearningCollector()

    # Model info
    model_file = updater.model_dir / "universal_element_classifier.pkl"
    model_exists = model_file.exists()
    model_size = model_file.stat().st_size / (1024 * 1024) if model_exists else 0

    current_version = updater._get_current_version()

    # Contribution status
    config_manager = ConfigManager()
    is_contributing = config_manager.get("ml.contribute", True)

    # Cache info
    total_samples = collector.get_local_samples_count()

    # Display
    info_text = f"""[bold]ML Model:[/bold]
• Version: {current_version}
• File: {model_file}
• Size: {model_size:.1f} MB
• Status: {'✅ Installed' if model_exists else '❌ Not found'}

[bold]Data Contribution:[/bold]
• Status: {'✅ Enabled' if is_contributing else '❌ Disabled'}
• Cached samples: {total_samples}
• Cache directory: {collector.local_cache_dir}

[bold]Endpoints:[/bold]
• Model updates: {updater.update_endpoint}
• Sample upload: {collector.upload_endpoint}

[bold]Commands:[/bold]
• Check updates: [cyan]observe ml check-updates[/cyan]
• Update model: [cyan]observe ml update-model[/cyan]
• View stats: [cyan]observe ml stats[/cyan]
• Enable contribution: [cyan]observe ml contribute --enable[/cyan]
"""

    console.print(Panel(info_text, title="ML System Information", border_style="cyan"))


if __name__ == "__main__":
    # Commands are registered in main.py
    pass
