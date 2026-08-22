"""
Device pool management for parallel test execution
"""

import json
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Any

from framework.domain import Platform

from .device_layer import Device, DeviceCapabilities, DeviceStatus, DeviceType


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
    # Single reentrant pool lock guarding device membership, the reserved map,
    # and the round-robin index. Reentrant so acquire_device can call the
    # strategy helpers while already holding it.
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def add_device(self, device: Device, verbose: bool = True) -> None:
        """Add device to pool"""
        with self._lock:
            if device.id not in [d.id for d in self.devices]:
                self.devices.append(device)
                self._locks[device.id] = threading.Lock()
                self._reserved[device.id] = False
                if verbose:
                    print(f"  Added {device.name} to pool '{self.name}'")

    def remove_device(self, device_id: str) -> None:
        """Remove device from pool"""
        with self._lock:
            self.devices = [d for d in self.devices if d.id != device_id]
            if device_id in self._locks:
                del self._locks[device_id]
            if device_id in self._reserved:
                del self._reserved[device_id]

    def get_available_count(self) -> int:
        """Get number of available devices"""
        with self._lock:
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
        # Filtering, strategy selection and reservation are done atomically
        # under the single pool lock so a concurrent add/remove/release cannot
        # scramble the candidate list, the round-robin index or the reserved map.
        with self._lock:
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

            if device is None:
                return None

            device_id = device.id
            # Double-check device still exists and is not reserved
            if not self._reserved.get(device_id, False):
                self._reserved[device_id] = True
                device.status = DeviceStatus.BUSY
                print(f"  Acquired device: {device.name} ({device.id})")
                return device

        return None

    def release_device(self, device_id: str) -> None:
        """Release (unreserve) a device back to the pool"""
        with self._lock:
            if device_id in self._reserved:
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
        """Round-robin device selection.

        Rotates over a *stable* ordering (the full pool device list) rather than
        over the shrinking ``candidates`` list, so that reserving devices does not
        scramble the index -> device mapping. Only devices that are still in
        ``candidates`` are eligible; the first eligible device after the last used
        index is chosen.
        """
        if not candidates:
            return None

        with self._lock:
            # Use the full device list as the stable rotation ordering. Fall back
            # to the candidates themselves when the pool list is empty (e.g. unit
            # tests that pass candidates not added to the pool).
            ordering = self.devices if self.devices else candidates
            n = len(ordering)
            if n == 0:
                return None

            candidate_ids = {d.id for d in candidates}
            for step in range(1, n + 1):
                idx = (self._last_used_index + step) % n
                device = ordering[idx]
                if device.id in candidate_ids:
                    self._last_used_index = idx
                    return device

            # No ordering member is currently a candidate; fall back safely.
            return candidates[0]

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


def _enum(enum_cls: Any, value: Any, default: Any) -> Any:
    """Resolve an enum from its wire value, falling back to a default on anything unknown."""
    try:
        return enum_cls(value)
    except ValueError:
        return default


def device_from_info(info: Dict[str, Any]) -> Device:
    """Build a driver-less :class:`Device` from a device dict (as returned by
    :class:`DeviceManager` or by :meth:`Device.to_dict`), for pool membership. It carries
    identity, platform and status for allocation bookkeeping; a live driver is attached
    later, when a test actually acquires the device."""
    platform = _enum(Platform, str(info.get("platform", "android")).lower(), Platform.ANDROID)
    default_type = DeviceType.SIMULATOR if platform == Platform.IOS else DeviceType.EMULATOR
    device_type = _enum(DeviceType, str(info.get("type", "")).lower(), default_type)
    version = str(info.get("platform_version") or info.get("api_level") or info.get("ios_version") or "")
    udid = str(info.get("id") or info.get("device_id") or "")
    caps = DeviceCapabilities(
        platform=platform,
        platform_version=version,
        device_name=str(info.get("name") or udid),
        udid=udid,
        device_type=device_type,
    )
    device = Device(caps, driver=None)
    device.status = _enum(DeviceStatus, str(info.get("status", "")).lower(), DeviceStatus.AVAILABLE)
    return device


def _pool_to_dict(pool: DevicePool) -> Dict[str, Any]:
    return {
        "name": pool.name,
        "strategy": pool.strategy.value,
        "devices": [d.to_dict() for d in pool.devices],
    }


class PoolManager:
    """Manages multiple device pools, persisted to disk so pools created by one command
    (``pool create``) are visible to the next (``pool list``, allocation)."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.pools: Dict[str, DevicePool] = {}
        self.storage_path = Path(storage_path) if storage_path else self._default_path()
        self._load()

    @staticmethod
    def _default_path() -> Path:
        env = os.environ.get("MOBISCOUT_POOLS_PATH")
        return Path(env) if env else Path.home() / ".mobiscout" / "pools.json"

    def _load(self) -> None:
        """Load persisted pools; a missing or unreadable store just starts empty."""
        if not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for pd in data.get("pools", []):
            strategy = _enum(PoolStrategy, pd.get("strategy", "round_robin"), PoolStrategy.ROUND_ROBIN)
            pool = DevicePool(name=pd["name"], strategy=strategy)
            for dd in pd.get("devices", []):
                pool.add_device(device_from_info(dd), verbose=False)
            self.pools[pool.name] = pool

    def save(self) -> None:
        """Persist every pool's membership + strategy to the JSON store."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pools": [_pool_to_dict(p) for p in self.pools.values()]}
        self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def create_pool(self, name: str, strategy: PoolStrategy = PoolStrategy.ROUND_ROBIN) -> DevicePool:
        """Create a new device pool"""
        if name in self.pools:
            raise ValueError(f"Pool '{name}' already exists")

        pool = DevicePool(name=name, strategy=strategy)
        self.pools[name] = pool
        self.save()
        print(f"Created device pool: '{name}' with strategy: {strategy.value}")
        return pool

    def get_pool(self, name: str) -> Optional[DevicePool]:
        """Get pool by name"""
        return self.pools.get(name)

    def delete_pool(self, name: str) -> None:
        """Delete a pool"""
        if name in self.pools:
            del self.pools[name]
            self.save()
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
