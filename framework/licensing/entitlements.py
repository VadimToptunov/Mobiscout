"""
Entitlements — the open-core seam between the free public engine and paid tiers.

The public Mobiscout is MIT and fully functional: **by default every limit is
unlimited**, so nothing here paywalls the OSS engine (the in-repo licence gate was
deliberately removed in the honesty cleanup, and this does not bring it back). What
it defines is *where* a paid distribution — the private Mobiscout-PRO package, or a
hosted deployment — can plug in limits and unlock premium features, via
``set_provider()``.

The enforcement helpers (``cap_screens``, ``cap_tests``, ``allow_targets``,
``has_feature``) are **no-ops** under the default UNLIMITED entitlements; they only
narrow behaviour once a provider installs a limited tier. So call sites can adopt
them now without changing the free engine at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional


class Tier(str, Enum):
    """Product tier."""

    FREE = "free"
    PRO = "pro"


@dataclass(frozen=True)
class Entitlements:
    """What the current tier is allowed to do. ``None`` limits mean unlimited; the
    ``"*"`` feature flag unlocks everything."""

    tier: Tier = Tier.FREE
    max_screens: Optional[int] = None  # screens mapped per crawl
    max_tests: Optional[int] = None  # generated test cases per kit
    max_targets: Optional[int] = None  # codegen languages/targets
    features: frozenset = frozenset()  # premium feature flags unlocked

    def has_feature(self, name: str) -> bool:
        return "*" in self.features or name in self.features


# The OSS default: unlimited and fully unlocked — the public engine is never crippled.
UNLIMITED = Entitlements(tier=Tier.PRO, features=frozenset({"*"}))


def _default_provider() -> Entitlements:
    return UNLIMITED


_provider: Callable[[], Entitlements] = _default_provider


def set_provider(provider: Callable[[], Entitlements]) -> None:
    """Install the entitlements source. A paid distribution injects real limits
    here (per licence); the OSS engine leaves it at UNLIMITED."""
    global _provider
    _provider = provider


def reset_provider() -> None:
    """Restore the default (UNLIMITED) provider — used by tests."""
    global _provider
    _provider = _default_provider


def entitlements() -> Entitlements:
    """The current entitlements; never raises — a broken provider degrades to
    UNLIMITED so a paid-layer bug can't brick the free engine."""
    try:
        return _provider() or UNLIMITED
    except Exception:
        return UNLIMITED


# --- enforcement helpers: no-ops under UNLIMITED, honoured when a provider limits --


def cap_screens(n: int) -> int:
    """Clamp a screen count to the tier's limit (unchanged if unlimited)."""
    limit = entitlements().max_screens
    return min(n, limit) if limit is not None else n


def cap_tests(n: int) -> int:
    """Clamp a generated-test count to the tier's limit (unchanged if unlimited)."""
    limit = entitlements().max_tests
    return min(n, limit) if limit is not None else n


def allow_targets(requested: List[str]) -> List[str]:
    """Trim a list of codegen targets to the tier's language limit (order-preserving;
    unchanged if unlimited)."""
    limit = entitlements().max_targets
    return list(requested[:limit]) if limit is not None else list(requested)


def has_feature(name: str) -> bool:
    """Whether a premium feature is unlocked for the current tier."""
    return entitlements().has_feature(name)
