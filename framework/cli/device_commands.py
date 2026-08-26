"""
Device Management CLI commands

Commands for managing mobile devices and device pools.
"""

from typing import Any, Dict, List

import click
from rich.table import Table

from framework.cli.rich_output import print_header, print_info, print_success, print_error, console
from framework.devices.device_manager import DeviceManager
from framework.devices.device_pool import PoolManager, PoolStrategy, device_from_info

# The CLI's status vocabulary against what the tools actually report: adb says
# "device" (surfaced as "online"), "offline" or "unauthorized"; simctl says
# "booted" or "shutdown". Without this mapping --status available matched nothing.
# There is no "busy" — reservation is a device-pool concept, not a device state.
_STATUS_ALIASES = {
    "available": {"online", "booted"},
    "offline": {"offline", "shutdown", "unauthorized"},
}


@click.group(name="devices")
def devices() -> None:
    """📱 Device management commands"""


@devices.command()
@click.option(
    "--platform", "-p", type=click.Choice(["android", "ios", "all"]), default="all", help="Filter by platform"
)
@click.option(
    "--status", "-s", type=click.Choice(["available", "offline", "all"]), default="all", help="Filter by status"
)
def list(platform: str, status: str) -> None:
    """List available devices"""
    print_header("Available Devices")

    try:
        manager = DeviceManager()

        # Get Android devices
        android_devices: List[Dict[str, Any]] = []
        errors: List[str] = []
        if platform in ["android", "all"]:
            android_devices, error = manager.probe_android_devices()
            if error:
                errors.append(error)

        # Get iOS devices
        ios_devices: List[Dict[str, Any]] = []
        if platform in ["ios", "all"]:
            ios_devices, error = manager.probe_ios_simulators()
            if error:
                errors.append(error)

        all_devices = android_devices + ios_devices

        # A failed probe is not "no devices" — say which tool failed and why.
        for error in errors:
            print_error(f"Device listing failed: {error}")

        if not all_devices:
            print_info("No devices found")
            return

        # Filter by status if specified
        if status != "all":
            wanted = _STATUS_ALIASES[status]
            all_devices = [d for d in all_devices if d["status"].lower() in wanted]

        if not all_devices:
            print_info(f"No {status} devices found")
            return

        # Display devices in table
        table = Table(title=f"Devices ({len(all_devices)} found)")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="yellow")
        table.add_column("Platform", style="blue")
        table.add_column("Version", style="green")
        table.add_column("Status", style="bold")

        for device in all_devices:
            status_emoji = {"available": "✅", "busy": "🔄", "offline": "❌"}.get(device["status"].lower(), "❓")

            table.add_row(
                device["id"],
                device.get("name") or "Unknown",
                device["platform"],
                # api_level is an int for real Android devices; Rich requires a
                # string cell, so coerce it (an int here used to crash the command).
                str(device.get("api_level") or device.get("ios_version") or "Unknown"),
                f"{status_emoji} {device['status']}",
            )

        console.print(table)

        # Show counts by platform
        android_count = len([d for d in all_devices if d["platform"] == "android"])
        ios_count = len([d for d in all_devices if d["platform"] == "ios"])

        print_info("\n📊 Summary:")
        print_info(f"  Android: {android_count}")
        print_info(f"  iOS: {ios_count}")
        print_info(f"  Total: {len(all_devices)}")

    except Exception as e:
        print_error(f"Failed to list devices: {e}")
        raise click.Abort()


@devices.command()
@click.option("--device-id", "-d", required=True, help="Device ID to check")
def info(device_id: str) -> None:
    """Show detailed device information"""
    print_header(f"Device Info: {device_id}")

    try:
        manager = DeviceManager()

        # Try to find device. Probe rather than list so a broken adb/simctl is reported as
        # such — "not found" would otherwise blame the device for a tooling failure.
        devices, listing_error = manager.probe_all_devices("all")
        device = next((d for d in devices if d.get("id") == device_id), None)

        if not device:
            if listing_error:
                print_error(f"Device listing failed: {listing_error}")
            else:
                print_error(f"Device {device_id} not found")
            raise click.Abort()

        print_success("📱 Device Details:")
        print_info(f"  ID:         {device.get('id', device_id)}")
        print_info(f"  Name:       {device.get('name', 'Unknown')}")
        print_info(f"  Platform:   {device.get('platform', 'Unknown')}")
        print_info(f"  OS Version: {device.get('os_version', 'Unknown')}")
        print_info(f"  Status:     {device.get('status', 'Unknown')}")

        capabilities = device.get("capabilities", {})
        if capabilities:
            print_info("\n  Capabilities:")
            for key, value in capabilities.items():
                print_info(f"    {key}: {value}")

    except Exception as e:
        print_error(f"Failed to get device info: {e}")
        raise click.Abort()


@devices.command()
def health() -> None:
    """Check health of all devices"""
    print_header("Device Health Check")

    try:
        manager = DeviceManager()

        # Get all devices. probe_* reports *why* a listing failed, so a broken adb/simctl
        # isn't reported as the (identical-looking) "no devices found".
        all_devices, listing_error = manager.probe_all_devices("all")

        if listing_error:
            print_error(f"Device listing failed: {listing_error}")

        if not all_devices:
            print_info("No devices found")
            return

        print_info(f"Checking {len(all_devices)} devices...")

        # Check each device
        healthy = []
        unhealthy = []

        for device in all_devices:
            device_id = device.get("id", "")
            health_result = manager.check_device_health(device_id)
            is_healthy = health_result.get("healthy", False)

            if is_healthy:
                healthy.append(device)
            else:
                unhealthy.append(device)

        # Display results
        print_info("")
        if healthy:
            print_success(f"✅ Healthy devices: {len(healthy)}")
            for device in healthy:
                print_info(f"  • {device["id"]} ({device.get('name')})")

        if unhealthy:
            print_error(f"\n❌ Unhealthy devices: {len(unhealthy)}")
            for device in unhealthy:
                print_error(f"  • {device["id"]} ({device.get('name')})")

        # Summary
        health_percentage = (len(healthy) / len(all_devices) * 100) if all_devices else 0
        print_info(f"\n📊 Overall health: {health_percentage:.1f}%")

    except Exception as e:
        print_error(f"Health check failed: {e}")
        raise click.Abort()


@devices.group(name="pool")
def pool() -> None:
    """Device pool management"""


@pool.command(name="create")
@click.option("--name", "-n", required=True, help="Pool name")
@click.option("--devices", "-d", required=True, help="Comma-separated device IDs")
@click.option(
    "--strategy",
    "-s",
    type=click.Choice(["round-robin", "least-busy", "random"]),
    default="round-robin",
    help="Device selection strategy",
)
def pool_create(name: str, devices: str, strategy: str) -> None:
    """Create a new device pool"""
    print_header(f"Creating Device Pool: {name}")

    try:
        manager = PoolManager()
        device_ids = [d.strip() for d in devices.split(",")]

        print_info(f"Pool name: {name}")
        print_info(f"Strategy: {strategy}")
        print_info(f"Devices: {len(device_ids)}")

        # Parse strategy
        strategy_map = {
            "round-robin": PoolStrategy.ROUND_ROBIN,
            "least-busy": PoolStrategy.LEAST_BUSY,
            "random": PoolStrategy.RANDOM,
        }
        pool_strategy = strategy_map[strategy]

        # Create pool
        new_pool = manager.create_pool(name, pool_strategy)

        # Add devices — build a real Device for each id and register it in the pool,
        # then persist so `pool list` and later allocation actually see the members.
        device_manager = DeviceManager()
        added = 0

        for device_id in device_ids:
            device_info = device_manager.get_device(device_id)
            if device_info:
                new_pool.add_device(device_from_info(device_info))
                added += 1
            else:
                print_error(f"  Warning: Device {device_id} not found")

        manager.save()
        print_success(f"✅ Created pool '{name}' with {added} devices")

    except Exception as e:
        print_error(f"Failed to create pool: {e}")
        raise click.Abort()


@pool.command(name="list")
def pool_list() -> None:
    """List all device pools"""
    print_header("Device Pools")

    try:
        manager = PoolManager()
        manager.list_pools()  # This method already prints to console

    except Exception as e:
        print_error(f"Failed to list pools: {e}")
        raise click.Abort()


@pool.command(name="info")
@click.argument("pool_name")
def pool_info(pool_name: str) -> None:
    """Show device pool information"""
    print_header(f"Pool Info: {pool_name}")

    try:
        manager = PoolManager()
        pool = manager.pools.get(pool_name)

        if not pool:
            print_error(f"Pool '{pool_name}' not found")
            raise click.Abort()

        print_success("📦 Pool Details:")
        print_info(f"  Name:     {pool_name}")
        print_info(f"  Strategy: {pool.strategy.value}")
        print_info(f"  Devices:  {len(pool.devices)}")

        if pool.devices:
            print_info("\n  Device List:")
            for device in pool.devices:
                status_emoji = {"available": "✅", "busy": "🔄", "offline": "❌"}.get(device.status.value.lower(), "❓")
                print_info(f"    {status_emoji} {device.id} ({device.name})")

        # Health check
        health = pool.health_check()
        print_info("\n  Health:")
        # These are the keys health_check() actually returns; reading 'available' /
        # 'busy' here made every `pool info` run abort with a KeyError.
        print_info(f"    Total: {health['total']}")
        print_info(f"    Healthy: {health['healthy']}")
        print_info(f"    Offline: {health['offline']}")
        print_info(f"    Utilization: {health['utilization']:.1%}")

    except Exception as e:
        print_error(f"Failed to get pool info: {e}")
        raise click.Abort()


@pool.command(name="delete")
@click.argument("pool_name")
@click.option("--force", "-f", is_flag=True, help="Force deletion without confirmation")
def pool_delete(pool_name: str, force: bool) -> None:
    """Delete a device pool"""
    print_header(f"Deleting Pool: {pool_name}")

    if not force:
        confirm = click.confirm(f"Are you sure you want to delete pool '{pool_name}'?")
        if not confirm:
            print_info("Cancelled")
            return

    try:
        manager = PoolManager()
        manager.delete_pool(pool_name)
        print_success(f"✅ Deleted pool '{pool_name}'")

    except Exception as e:
        print_error(f"Failed to delete pool: {e}")
        raise click.Abort()


if __name__ == "__main__":
    devices()
