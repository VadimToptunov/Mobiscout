"""
Device pool management for parallel test execution
"""

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Any

from .device_layer import Device, DeviceStatus, DeviceType


class PoolStrategy(Enum):
    """Strategy for device allocation"""

    ROUND_ROBIN = "round_robin"
    LEAST_BUSY = "least_busy"
    RANDOM = "random"
    PRIORITY = "priority"


@dataclass
class DevicePool:
    """
    Manages a pool of devices for parallel test execution

    Features:
    - Device reservation and locking
    - Load balancing
    - Health monitoring
    - Automatic recovery
    """

    name: str
    devices: List[Device] = field(default_factory=list)
    strategy: PoolStrategy = PoolStrategy.ROUND_ROBIN

    # Internal state
    _locks: Dict[str, threading.Lock] = field(default_factory=dict)
    _reserved: Dict[str, bool] = field(default_factory=dict)
    _last_used_index: int = 0

    def add_device(self, device: Device) -> None:
        """Add device to pool"""
        if device.id not in [d.id for d in self.devices]:
            self.devices.append(device)
            self._locks[device.id] = threading.Lock()
            self._reserved[device.id] = False
            print(f"  Added {device.name} to pool '{self.name}'")

    def remove_device(self, device_id: str) -> None:
        """Remove device from pool"""
        self.devices = [d for d in self.devices if d.id != device_id]
        if device_id in self._locks:
            del self._locks[device_id]
        if device_id in self._reserved:
            del self._reserved[device_id]

    def get_available_count(self) -> int:
        """Get number of available devices"""
        return sum(
            1
            for device in self.devices
            if not self._reserved.get(device.id, False) and device.status == DeviceStatus.AVAILABLE
        )

    def acquire_device(self, filters: Optional[Dict] = None) -> Optional[Device]:
        """
        Acquire (reserve) a device from the pool

        Args:
            filters: Optional filters (platform, model, version, etc.)

        Returns:
            Reserved device or None if no devices available
        """
        # Filter devices
        candidates = self._filter_devices(filters)

        if not candidates:
            return None

        # Apply strategy
        if self.strategy == PoolStrategy.ROUND_ROBIN:
            device = self._acquire_round_robin(candidates)
        elif self.strategy == PoolStrategy.LEAST_BUSY:
            device = self._acquire_least_busy(candidates)
        elif self.strategy == PoolStrategy.RANDOM:
            import random

            device = random.choice(candidates) if candidates else None
        else:
            device = candidates[0] if candidates else None

        if device:
            # Get lock reference while holding no locks to avoid race
            device_id = device.id
            if device_id not in self._locks:
                return None
            lock = self._locks[device_id]

            with lock:
                # Double-check device still exists and is not reserved
                if device_id not in self._reserved:
                    return None
                if not self._reserved[device_id]:
                    self._reserved[device_id] = True
                    device.status = DeviceStatus.BUSY
                    print(f"  Acquired device: {device.name} ({device.id})")
                    return device

        return None

    def release_device(self, device_id: str) -> None:
        """Release (unreserve) a device back to the pool"""
        if device_id in self._reserved:
            with self._locks[device_id]:
                self._reserved[device_id] = False

                # Update device status
                for device in self.devices:
                    if device.id == device_id:
                        device.status = DeviceStatus.AVAILABLE
                        print(f"  Released device: {device.name} ({device_id})")
                        break

    def _filter_devices(self, filters: Optional[Dict]) -> List[Device]:
        """Filter available devices by criteria"""
        # Start with available devices
        candidates = [
            d for d in self.devices if not self._reserved.get(d.id, False) and d.status == DeviceStatus.AVAILABLE
        ]

        if not filters:
            return candidates

        # Apply filters
        if "platform" in filters:
            candidates = [d for d in candidates if d.platform == filters["platform"]]

        if "type" in filters:
            device_type = DeviceType(filters["type"]) if isinstance(filters["type"], str) else filters["type"]
            candidates = [d for d in candidates if d.type == device_type]

        if "model" in filters:
            model = filters["model"].lower()
            candidates = [d for d in candidates if model in (d.model or "").lower()]

        if "min_version" in filters:
            # Use proper semantic version comparison instead of string comparison
            min_version = filters["min_version"]
            candidates = [d for d in candidates if self._compare_versions(d.platform_version, min_version) >= 0]

        return candidates

    def _compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings semantically

        Args:
            version1: First version string (e.g., "13.0", "10.5.2")
            version2: Second version string

        Returns:
            -1 if version1 < version2
             0 if version1 == version2
             1 if version1 > version2
        """
        try:
            # Split versions and convert to integers
            parts1 = [int(x) for x in version1.split(".")]
            parts2 = [int(x) for x in version2.split(".")]

            # Pad shorter version with zeros
            max_len = max(len(parts1), len(parts2))
            parts1 += [0] * (max_len - len(parts1))
            parts2 += [0] * (max_len - len(parts2))

            # Compare component by component
            for p1, p2 in zip(parts1, parts2):
                if p1 < p2:
                    return -1
                elif p1 > p2:
                    return 1
            return 0
        except (ValueError, AttributeError):
            # Fallback to string comparison if parsing fails
            if version1 < version2:
                return -1
            elif version1 > version2:
                return 1
            return 0

    def _acquire_round_robin(self, candidates: List[Device]) -> Optional[Device]:
        """Round-robin device selection"""
        if not candidates:
            return None

        # Find next device after last used index
        # Guard against empty list (though checked above, for safety)
        num_candidates = len(candidates)
        if num_candidates == 0:
            return None
        self._last_used_index = (self._last_used_index + 1) % num_candidates
        return candidates[self._last_used_index]

    def _acquire_least_busy(self, candidates: List[Device]) -> Optional[Device]:
        """Select least busy device (for future use with metrics)"""
        # For now, just return first available
        # TODO: Track device usage metrics and select least busy
        return candidates[0] if candidates else None

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on all devices in pool"""
        healthy = 0
        unhealthy = 0
        offline = 0

        for device in self.devices:
            if device.status == DeviceStatus.AVAILABLE:
                healthy += 1
            elif device.status == DeviceStatus.OFFLINE:
                offline += 1
            else:
                unhealthy += 1

        return {
            "total": len(self.devices),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "offline": offline,
            "utilization": (len(self.devices) - healthy) / len(self.devices) if self.devices else 0,
        }

    def to_dict(self) -> Dict:
        """Convert pool to dictionary"""
        health = self.health_check()
        return {
            "name": self.name,
            "strategy": self.strategy.value,
            "total_devices": len(self.devices),
            "available_devices": self.get_available_count(),
            "health": health,
            "devices": [d.to_dict() for d in self.devices],
        }


class PoolManager:
    """Manages multiple device pools"""

    def __init__(self) -> None:
        self.pools: Dict[str, DevicePool] = {}

    def create_pool(self, name: str, strategy: PoolStrategy = PoolStrategy.ROUND_ROBIN) -> DevicePool:
        """Create a new device pool"""
        if name in self.pools:
            raise ValueError(f"Pool '{name}' already exists")

        pool = DevicePool(name=name, strategy=strategy)
        self.pools[name] = pool
        print(f"Created device pool: '{name}' with strategy: {strategy.value}")
        return pool

    def get_pool(self, name: str) -> Optional[DevicePool]:
        """Get pool by name"""
        return self.pools.get(name)

    def delete_pool(self, name: str) -> None:
        """Delete a pool"""
        if name in self.pools:
            del self.pools[name]
            print(f"Deleted pool: '{name}'")

    def list_pools(self) -> None:
        """Print all pools"""
        if not self.pools:
            print("No device pools created.")
            return

        print(f"\nDevice Pools ({len(self.pools)}):")
        print(f"{'=' * 80}\n")

        for name, pool in self.pools.items():
            health = pool.health_check()
            print(f"  Pool: {name}")
            print(f"    Strategy: {pool.strategy.value}")
            print(f"    Devices: {len(pool.devices)} total, {pool.get_available_count()} available")
            print(f"    Health: {health['healthy']} healthy, {health['offline']} offline")
            print(f"    Utilization: {health['utilization']:.1%}")
            print()
