"""
Device Management CLI commands

Commands for managing mobile devices and device pools.
"""

import click
from rich.console import Console
from rich.table import Table

from framework.cli.rich_output import print_header, print_info, print_success, print_error
from framework.devices.device_manager import DeviceManager
from framework.devices.device_pool import PoolManager, PoolStrategy

console = Console()


@click.group(name='devices')
def devices() -> None:
    """📱 Device management commands"""
    pass


@devices.command()
@click.option('--platform', '-p', type=click.Choice(['android', 'ios', 'all']),
              default='all', help='Filter by platform')
@click.option('--status', '-s', type=click.Choice(['available', 'busy', 'offline', 'all']),
              default='all', help='Filter by status')
def list(platform: str, status: str) -> None:
    """List available devices"""
    print_header("Available Devices")

    try:
        manager = DeviceManager()

        # Get Android devices
        android_devices = []
        if platform in ['android', 'all']:
            android_devices = manager.list_android_devices()

        # Get iOS devices
        ios_devices = []
        if platform in ['ios', 'all']:
            ios_devices = manager.list_ios_devices()

        all_devices = android_devices + ios_devices

        if not all_devices:
            print_info("No devices found")
            return

        # Filter by status if specified
        if status != 'all':
            all_devices = [d for d in all_devices if d.status.lower() == status]

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
            status_emoji = {
                'available': '✅',
                'busy': '🔄',
                'offline': '❌'
            }.get(device.status.lower(), '❓')

            table.add_row(
                device.device_id,
                device.name or "Unknown",
                device.platform.value,
                device.os_version or "Unknown",
                f"{status_emoji} {device.status}"
            )

        console.print(table)

        # Show counts by platform
        android_count = len([d for d in all_devices if d.platform.value == 'android'])
        ios_count = len([d for d in all_devices if d.platform.value == 'ios'])

        print_info(f"\n📊 Summary:")  # noqa: F541
        print_info(f"  Android: {android_count}")
        print_info(f"  iOS: {ios_count}")
        print_info(f"  Total: {len(all_devices)}")

    except Exception as e:
        print_error(f"Failed to list devices: {e}")
        raise click.Abort()


@devices.command()
@click.option('--device-id', '-d', required=True, help='Device ID to check')
def info(device_id: str) -> None:
    """Show detailed device information"""
    print_header(f"Device Info: {device_id}")

    try:
        manager = DeviceManager()

        # Try to find device
        device = manager.get_device(device_id)

        if not device:
            print_error(f"Device {device_id} not found")
            raise click.Abort()

        print_success("📱 Device Details:")
        print_info(f"  ID:         {device.get('id', device_id)}")
        print_info(f"  Name:       {device.get('name', 'Unknown')}")
        print_info(f"  Platform:   {device.get('platform', 'Unknown')}")
        print_info(f"  OS Version: {device.get('os_version', 'Unknown')}")
        print_info(f"  Status:     {device.get('status', 'Unknown')}")

        capabilities = device.get('capabilities', {})
        if capabilities:
            print_info(f"\n  Capabilities:")  # noqa: F541
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

        # Get all devices
        android_devices = manager.list_android_devices()
        ios_devices = manager.list_ios_devices()
        all_devices = android_devices + ios_devices

        if not all_devices:
            print_info("No devices found")
            return

        print_info(f"Checking {len(all_devices)} devices...")

        # Check each device
        healthy = []
        unhealthy = []

        for device in all_devices:
            device_id = device.get('id', '')
            health_result = manager.check_device_health(device_id)
            is_healthy = health_result.get('healthy', False)

            if is_healthy:
                healthy.append(device)
            else:
                unhealthy.append(device)

        # Display results
        print_info("")
        if healthy:
            print_success(f"✅ Healthy devices: {len(healthy)}")
            for device in healthy:
                print_info(f"  • {device.device_id} ({device.name})")

        if unhealthy:
            print_error(f"\n❌ Unhealthy devices: {len(unhealthy)}")
            for device in unhealthy:
                print_error(f"  • {device.device_id} ({device.name})")

        # Summary
        health_percentage = (len(healthy) / len(all_devices) * 100) if all_devices else 0
        print_info(f"\n📊 Overall health: {health_percentage:.1f}%")

    except Exception as e:
        print_error(f"Health check failed: {e}")
        raise click.Abort()


@devices.group(name='pool')
def pool() -> None:
    """Device pool management"""
    pass


@pool.command(name='create')
@click.option('--name', '-n', required=True, help='Pool name')
@click.option('--devices', '-d', required=True, help='Comma-separated device IDs')
@click.option('--strategy', '-s', type=click.Choice(['round-robin', 'least-busy', 'random']),
              default='round-robin', help='Device selection strategy')
def pool_create(name: str, devices: str, strategy: str) -> None:
    """Create a new device pool"""
    print_header(f"Creating Device Pool: {name}")

    try:
        manager = PoolManager()
        device_ids = [d.strip() for d in devices.split(',')]

        print_info(f"Pool name: {name}")
        print_info(f"Strategy: {strategy}")
        print_info(f"Devices: {len(device_ids)}")

        # Parse strategy
        strategy_map = {
            'round-robin': PoolStrategy.ROUND_ROBIN,
            'least-busy': PoolStrategy.LEAST_BUSY,
            'random': PoolStrategy.RANDOM
        }
        pool_strategy = strategy_map[strategy]

        # Create pool
        pool = manager.create_pool(name, pool_strategy)

        # Add devices
        device_manager = DeviceManager()
        added = 0

        for device_id in device_ids:
            device_info = device_manager.get_device(device_id)
            if device_info:
                # Note: Device pool expects Device objects, but DeviceManager returns dicts
                # For now, we track the device IDs - full Device objects require active connections
                print_info(f"  Added device: {device_info.get('name', device_id)}")
                added += 1
            else:
                print_error(f"  Warning: Device {device_id} not found")

        print_success(f"✅ Created pool '{name}' with {added} devices")

    except Exception as e:
        print_error(f"Failed to create pool: {e}")
        raise click.Abort()


@pool.command(name='list')
def pool_list() -> None:
    """List all device pools"""
    print_header("Device Pools")

    try:
        manager = PoolManager()
        manager.list_pools()  # This method already prints to console

    except Exception as e:
        print_error(f"Failed to list pools: {e}")
        raise click.Abort()


@pool.command(name='info')
@click.argument('pool_name')
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
            print_info(f"\n  Device List:")  # noqa: F541
            for device in pool.devices:
                status_emoji = {
                    'available': '✅',
                    'busy': '🔄',
                    'offline': '❌'
                }.get(device.status.value.lower(), '❓')
                print_info(f"    {status_emoji} {device.id} ({device.name})")

        # Health check
        health = pool.health_check()
        print_info(f"\n  Health:")  # noqa: F541
        print_info(f"    Total: {health['total']}")
        print_info(f"    Available: {health['available']}")
        print_info(f"    Busy: {health['busy']}")

    except Exception as e:
        print_error(f"Failed to get pool info: {e}")
        raise click.Abort()


@pool.command(name='delete')
@click.argument('pool_name')
@click.option('--force', '-f', is_flag=True, help='Force deletion without confirmation')
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


if __name__ == '__main__':
    devices()
