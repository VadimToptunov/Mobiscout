"""Tests for framework.devices.device_pool.

Guards pool state transitions and allocation logic: adding/removing devices,
reserve/release flipping availability and device status, filtering by
platform/type/model/min_version, semantic version comparison, round-robin
rotation, the health-check/to_dict snapshots, and PoolManager lifecycle
(create/get/delete plus duplicate-name rejection).
"""

import pytest

from framework.devices.device_layer import (
    Device,
    DeviceCapabilities,
    DeviceStatus,
    DeviceType,
)
from framework.devices.device_pool import DevicePool, PoolManager, PoolStrategy
from framework.domain import Platform


def _device(
    udid: str,
    name: str = "Pixel",
    platform: Platform = Platform.ANDROID,
    version: str = "13.0",
    dtype: DeviceType = DeviceType.EMULATOR,
    model: str = "Pixel 6",
) -> Device:
    caps = DeviceCapabilities(
        platform=platform,
        platform_version=version,
        device_name=model,
        udid=udid,
        device_type=dtype,
    )
    dev = Device(capabilities=caps, driver=None)
    dev.status = DeviceStatus.AVAILABLE
    return dev


def test_add_device_is_idempotent():
    pool = DevicePool(name="p")
    d = _device("u1")
    pool.add_device(d)
    pool.add_device(d)  # same id -> ignored
    assert len(pool.devices) == 1
    assert pool.get_available_count() == 1


def test_remove_device_clears_state():
    pool = DevicePool(name="p")
    pool.add_device(_device("u1"))
    pool.remove_device("u1")
    assert pool.devices == []
    assert "u1" not in pool._locks
    assert "u1" not in pool._reserved


def test_acquire_and_release_flip_status():
    pool = DevicePool(name="p")
    pool.add_device(_device("u1"))
    assert pool.get_available_count() == 1

    dev = pool.acquire_device()
    assert dev is not None and dev.id == "u1"
    assert dev.status == DeviceStatus.BUSY
    assert pool._reserved["u1"] is True
    assert pool.get_available_count() == 0

    pool.release_device("u1")
    assert pool._reserved["u1"] is False
    assert dev.status == DeviceStatus.AVAILABLE
    assert pool.get_available_count() == 1


def test_acquire_returns_none_when_empty():
    assert DevicePool(name="p").acquire_device() is None


def test_acquire_all_then_none_left():
    pool = DevicePool(name="p")
    pool.add_device(_device("u1"))
    pool.add_device(_device("u2"))
    first = pool.acquire_device()
    second = pool.acquire_device()
    assert {first.id, second.id} == {"u1", "u2"}
    assert pool.acquire_device() is None


def test_filter_by_platform_and_type():
    pool = DevicePool(name="p")
    pool.add_device(_device("a", platform=Platform.ANDROID, dtype=DeviceType.EMULATOR))
    pool.add_device(_device("i", platform=Platform.IOS, dtype=DeviceType.SIMULATOR))

    dev = pool.acquire_device(filters={"platform": Platform.IOS})
    assert dev is not None and dev.id == "i"

    dev2 = pool.acquire_device(filters={"type": "emulator"})
    assert dev2 is not None and dev2.id == "a"


def test_filter_by_model_substring():
    pool = DevicePool(name="p")
    pool.add_device(_device("a", model="Galaxy S21"))
    pool.add_device(_device("b", model="Pixel 7"))
    dev = pool.acquire_device(filters={"model": "pixel"})
    assert dev is not None and dev.id == "b"


def test_filter_by_min_version():
    pool = DevicePool(name="p")
    pool.add_device(_device("old", version="11.0"))
    pool.add_device(_device("new", version="14.0"))
    dev = pool.acquire_device(filters={"min_version": "13.0"})
    assert dev is not None and dev.id == "new"


def test_filter_no_match_returns_none():
    pool = DevicePool(name="p")
    pool.add_device(_device("a", platform=Platform.ANDROID))
    assert pool.acquire_device(filters={"platform": Platform.IOS}) is None


def test_compare_versions_semantics():
    pool = DevicePool(name="p")
    assert pool._compare_versions("13.0", "9.0") == 1  # numeric, not lexical
    assert pool._compare_versions("10.5.2", "10.5.2") == 0
    assert pool._compare_versions("9.0", "10.0") == -1


def test_round_robin_rotates_over_candidates():
    pool = DevicePool(name="p", strategy=PoolStrategy.ROUND_ROBIN)
    candidates = [_device("a"), _device("b"), _device("c")]
    picks = [pool._acquire_round_robin(candidates).id for _ in range(6)]
    # each of the three candidates gets selected as we cycle
    assert set(picks) == {"a", "b", "c"}
    # deterministic cycle of period 3
    assert picks[0] == picks[3] and picks[1] == picks[4]


def test_round_robin_acquires_distinct_devices_in_order():
    # Bug 6: round-robin indexed into a shrinking candidate list, so reserving
    # devices scrambled the index -> device mapping and could repeat/skip.
    pool = DevicePool(name="p", strategy=PoolStrategy.ROUND_ROBIN)
    pool.add_device(_device("a"))
    pool.add_device(_device("b"))
    pool.add_device(_device("c"))

    picks = [pool.acquire_device().id for _ in range(3)]
    assert sorted(picks) == ["a", "b", "c"]  # all three, each exactly once
    assert pool.acquire_device() is None  # pool exhausted


def test_round_robin_no_keyerror_under_add_and_remove():
    # Bug 6: membership/index mutated without a lock -> KeyError/arbitrary picks.
    pool = DevicePool(name="p", strategy=PoolStrategy.ROUND_ROBIN)
    for i in range(4):
        pool.add_device(_device(f"d{i}"))

    d1 = pool.acquire_device()
    assert d1 is not None
    # Remove a *different*, unreserved device mid-flight.
    to_remove = next(x for x in ["d0", "d1", "d2", "d3"] if x != d1.id)
    pool.remove_device(to_remove)

    # Release the acquired one, add a new one, keep acquiring — must not raise.
    pool.release_device(d1.id)
    pool.add_device(_device("d9"))

    acquired = []
    while True:
        dev = pool.acquire_device()
        if dev is None:
            break
        acquired.append(dev.id)

    # No device is handed out twice, and the removed one never appears.
    assert len(acquired) == len(set(acquired))
    assert to_remove not in acquired


def test_health_check_snapshot():
    pool = DevicePool(name="p")
    a = _device("a")
    b = _device("b")
    b.status = DeviceStatus.OFFLINE
    pool.add_device(a)
    pool.add_device(b)
    health = pool.health_check()
    assert health["total"] == 2
    assert health["healthy"] == 1
    assert health["offline"] == 1
    assert health["utilization"] == pytest.approx(0.5)


def test_to_dict_shape():
    pool = DevicePool(name="mypool", strategy=PoolStrategy.LEAST_BUSY)
    pool.add_device(_device("a"))
    d = pool.to_dict()
    assert d["name"] == "mypool"
    assert d["strategy"] == "least_busy"
    assert d["total_devices"] == 1
    assert d["available_devices"] == 1
    assert len(d["devices"]) == 1


def test_pool_manager_lifecycle():
    mgr = PoolManager()
    pool = mgr.create_pool("main", strategy=PoolStrategy.RANDOM)
    assert isinstance(pool, DevicePool)
    assert mgr.get_pool("main") is pool
    with pytest.raises(ValueError):
        mgr.create_pool("main")
    mgr.delete_pool("main")
    assert mgr.get_pool("main") is None
