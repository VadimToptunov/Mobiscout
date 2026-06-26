"""
License Management CLI Commands

STEP 7: Paid Modules Enhancement - CLI Interface
"""

from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from framework.licensing.enhanced_validator import (
    LicenseManager,
    LicenseTier,
    FeatureFlag,
    get_license_manager,
)

console = Console()


@click.group()
def license() -> None:
    """
    License management commands.

    Manage your Observe Framework license, view usage, and upgrade.
    """
    pass


@license.command()
def info() -> None:
    """
    Display current license information.

    Example:
        observe license info
    """
    manager = get_license_manager()
    info = manager.get_license_info()

    tier_colors = {
        'free': 'dim',
        'pro': 'cyan',
        'enterprise': 'gold1',
        'trial': 'magenta',
    }

    tier = info['tier']
    color = tier_colors.get(tier, 'white')

    console.print(Panel.fit(
        f"[{color} bold]{tier.upper()}[/{color} bold] License",
        title="Observe Framework License",
        border_style=color,
    ))

    table = Table(show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Status", "[green]Valid[/green]" if info['valid'] else "[red]Invalid[/red]")
    table.add_row("Tier", f"[{color}]{tier.upper()}[/{color}]")

    if info.get('email'):
        table.add_row("Email", info['email'])

    if info.get('organization'):
        table.add_row("Organization", info['organization'])

    if info.get('expires_at'):
        days_left = info.get('days_until_expiry', 0)
        if days_left and days_left > 30:
            expiry_style = "green"
        elif days_left and days_left > 7:
            expiry_style = "yellow"
        else:
            expiry_style = "red"
        table.add_row("Expires", f"[{expiry_style}]{info['expires_at']}[/{expiry_style}]")
        table.add_row("Days Left", f"[{expiry_style}]{days_left}[/{expiry_style}]")

    table.add_row("Max Users", str(info.get('max_users', 1)))
    table.add_row("Max Devices", str(info.get('max_devices', 5)))

    console.print(table)

    # Show enabled features
    console.print("\n[bold]Enabled Features:[/bold]")
    features = info.get('features', [])
    if features:
        for feature in features:
            console.print(f"  [green]✓[/green] {feature.replace('_', ' ').title()}")
    else:
        console.print("  [dim]No special features enabled[/dim]")


@license.command()
def usage() -> None:
    """
    Display usage statistics.

    Example:
        observe license usage
    """
    manager = get_license_manager()
    stats = manager.get_usage_stats()

    console.print(Panel.fit("📊 Usage Statistics", style="bold cyan"))

    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="yellow", justify="right")

    table.add_row("Tests Run", f"{stats.get('tests_run', 0):,}")
    table.add_row("Devices Connected", f"{stats.get('devices_connected', 0):,}")
    table.add_row("Screenshots Captured", f"{stats.get('screenshots_captured', 0):,}")
    table.add_row("API Calls Analyzed", f"{stats.get('api_calls_analyzed', 0):,}")
    table.add_row("ML Predictions", f"{stats.get('ml_predictions', 0):,}")
    table.add_row("Flow Discoveries", f"{stats.get('flow_discoveries', 0):,}")
    table.add_row("Sessions", f"{stats.get('session_count', 0):,}")
    table.add_row("Total Runtime", f"{stats.get('total_runtime_hours', 0):.1f} hours")

    if stats.get('last_used'):
        table.add_row("Last Used", stats['last_used'])

    console.print(table)


@license.command()
@click.argument("license_key")
@click.option("--email", "-e", required=True, help="Email address for license")
def activate(license_key: str, email: str) -> None:
    """
    Activate a license key.

    Example:
        observe license activate PRO-XXXXX-XXXXX --email user@example.com
        observe license activate ENT-XXXXX-XXXXX --email admin@company.com
    """
    manager = get_license_manager()

    console.print(f"[cyan]→[/cyan] Activating license...")

    if manager.activate_license(license_key, email):
        info = manager.get_license_info()
        console.print(f"\n[green]✓[/green] License activated successfully!")
        console.print(f"  Tier: [bold]{info['tier'].upper()}[/bold]")
        console.print(f"  Email: {email}")

        if info.get('expires_at'):
            console.print(f"  Expires: {info['expires_at']}")
    else:
        console.print("[red]✗[/red] Failed to activate license")
        console.print("  Please check your license key and try again.")
        raise SystemExit(1)


@license.command()
@click.option("--trial", is_flag=True, help="Start a 7-day PRO trial")
def upgrade(trial: bool) -> None:
    """
    Upgrade your license.

    Example:
        observe license upgrade --trial
        observe license upgrade
    """
    if trial:
        console.print(Panel.fit(
            "🎁 Start Your 7-Day PRO Trial",
            style="bold magenta",
        ))
        console.print()
        console.print("Get full access to PRO features for 7 days, no credit card required!")
        console.print()
        console.print("PRO Features:")
        console.print("  [green]✓[/green] Cloud device integration")
        console.print("  [green]✓[/green] Parallel test execution")
        console.print("  [green]✓[/green] Advanced ML features")
        console.print("  [green]✓[/green] API mocking")
        console.print("  [green]✓[/green] Load testing")
        console.print("  [green]✓[/green] Priority email support")
        console.print()
        console.print("[cyan]To start your trial, visit:[/cyan]")
        console.print("  https://yoursite.com/trial")
        console.print()
        console.print("Or run:")
        console.print("  observe license activate TRIAL-XXXXX --email your@email.com")
    else:
        console.print(Panel.fit("⚡ Upgrade Your License", style="bold cyan"))
        console.print()

        # PRO tier
        console.print("[bold cyan]💎 PRO License[/bold cyan]")
        console.print("  $49/month or $499/year (save 15%)")
        console.print()
        console.print("  Features:")
        console.print("    • Cloud device integration")
        console.print("    • Parallel test execution")
        console.print("    • Advanced ML features")
        console.print("    • API mocking")
        console.print("    • Load testing")
        console.print("    • Priority email support")
        console.print()

        # ENTERPRISE tier
        console.print("[bold gold1]🏢 ENTERPRISE License[/bold gold1]")
        console.print("  Contact sales for pricing")
        console.print()
        console.print("  Everything in PRO, plus:")
        console.print("    • ML model training")
        console.print("    • Custom models")
        console.print("    • Distributed execution")
        console.print("    • SSO & LDAP integration")
        console.print("    • On-premise deployment")
        console.print("    • Dedicated support & SLA")
        console.print("    • Security scanning")
        console.print("    • Performance profiling")
        console.print()

        console.print("[cyan]Visit:[/cyan] https://yoursite.com/pricing")


@license.command()
def features() -> None:
    """
    List all features by tier.

    Example:
        observe license features
    """
    console.print(Panel.fit("📋 Feature Comparison", style="bold cyan"))

    table = Table()
    table.add_column("Feature", style="white")
    table.add_column("FREE", style="dim", justify="center")
    table.add_column("PRO", style="cyan", justify="center")
    table.add_column("ENTERPRISE", style="gold1", justify="center")

    features_by_tier = {
        "Core Engine": (True, True, True),
        "Local Devices": (True, True, True),
        "Basic Test Generation": (True, True, True),
        "Self-Healing": (True, True, True),
        "Flow Discovery": (True, True, True),
        "ML Inference": (True, True, True),
        "Cloud Devices": (False, True, True),
        "Parallel Execution": (False, True, True),
        "Advanced ML": (False, True, True),
        "API Mocking": (False, True, True),
        "Load Testing": (False, True, True),
        "Priority Support": (False, True, True),
        "ML Training": (False, False, True),
        "Custom Models": (False, False, True),
        "Distributed Execution": (False, False, True),
        "SSO & LDAP": (False, False, True),
        "On-Premise": (False, False, True),
        "Dedicated Support": (False, False, True),
        "Security Scanning": (False, False, True),
        "Performance Profiling": (False, False, True),
    }

    for feature, (free, pro, enterprise) in features_by_tier.items():
        table.add_row(
            feature,
            "[green]✓[/green]" if free else "[dim]—[/dim]",
            "[green]✓[/green]" if pro else "[dim]—[/dim]",
            "[green]✓[/green]" if enterprise else "[dim]—[/dim]",
        )

    console.print(table)

    console.print()
    console.print("[dim]Pricing:[/dim]")
    console.print("  FREE: $0")
    console.print("  PRO: $49/month or $499/year")
    console.print("  ENTERPRISE: Contact sales")


@license.command()
@click.argument("feature_name")
def check(feature_name: str) -> None:
    """
    Check if a specific feature is available.

    Example:
        observe license check cloud_devices
        observe license check ml_training
    """
    manager = get_license_manager()

    # Map string to FeatureFlag
    feature_map = {
        'core_engine': FeatureFlag.CORE_ENGINE,
        'local_devices': FeatureFlag.LOCAL_DEVICES,
        'basic_test_gen': FeatureFlag.BASIC_TEST_GEN,
        'self_healing': FeatureFlag.SELF_HEALING,
        'flow_discovery': FeatureFlag.FLOW_DISCOVERY,
        'ml_inference': FeatureFlag.ML_INFERENCE,
        'cloud_devices': FeatureFlag.CLOUD_DEVICES,
        'parallel_execution': FeatureFlag.PARALLEL_EXECUTION,
        'advanced_ml': FeatureFlag.ADVANCED_ML,
        'api_mocking': FeatureFlag.API_MOCKING,
        'load_testing': FeatureFlag.LOAD_TESTING,
        'priority_support': FeatureFlag.PRIORITY_SUPPORT,
        'ml_training': FeatureFlag.ML_TRAINING,
        'custom_models': FeatureFlag.CUSTOM_MODELS,
        'distributed_execution': FeatureFlag.DISTRIBUTED_EXECUTION,
        'sso_ldap': FeatureFlag.SSO_LDAP,
        'on_premise': FeatureFlag.ON_PREMISE,
        'dedicated_support': FeatureFlag.DEDICATED_SUPPORT,
        'security_scanning': FeatureFlag.SECURITY_SCANNING,
        'performance_profiling': FeatureFlag.PERFORMANCE_PROFILING,
    }

    feature = feature_map.get(feature_name.lower())
    if not feature:
        console.print(f"[red]✗[/red] Unknown feature: {feature_name}")
        console.print("\nAvailable features:")
        for name in feature_map:
            console.print(f"  • {name}")
        raise SystemExit(1)

    if manager.check_feature(feature):
        console.print(f"[green]✓[/green] Feature '{feature_name}' is available")
    else:
        console.print(f"[red]✗[/red] Feature '{feature_name}' requires upgrade")

        # Show which tier is needed
        info = manager.get_license_info()
        console.print(f"\n  Current tier: {info['tier'].upper()}")

        # Determine required tier
        pro_features = [
            FeatureFlag.CLOUD_DEVICES, FeatureFlag.PARALLEL_EXECUTION,
            FeatureFlag.ADVANCED_ML, FeatureFlag.API_MOCKING,
            FeatureFlag.LOAD_TESTING, FeatureFlag.PRIORITY_SUPPORT,
        ]
        if feature in pro_features:
            console.print("  Required tier: [cyan]PRO[/cyan]")
        else:
            console.print("  Required tier: [gold1]ENTERPRISE[/gold1]")

        console.print("\n  Run 'observe license upgrade' for more info")


@license.command()
def deactivate() -> None:
    """
    Deactivate current license (revert to FREE).

    Example:
        observe license deactivate
    """
    manager = get_license_manager()
    info = manager.get_license_info()

    if info['tier'] == 'free':
        console.print("[dim]Already on FREE tier[/dim]")
        return

    if click.confirm(
        f"Are you sure you want to deactivate your {info['tier'].upper()} license?",
        default=False
    ):
        # Reset to free license
        manager.license = manager._create_free_license()
        manager.save_license()
        console.print("[green]✓[/green] License deactivated. Now on FREE tier.")
    else:
        console.print("[dim]Cancelled[/dim]")


if __name__ == "__main__":
    license()
