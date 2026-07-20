"""Open-core entitlements. Public engine defaults to unlimited; a paid layer
plugs limits in via ``set_provider`` (see :mod:`framework.licensing.entitlements`)."""

from framework.licensing.entitlements import (
    Entitlements,
    Tier,
    UNLIMITED,
    allow_targets,
    cap_screens,
    cap_tests,
    entitlements,
    has_feature,
    reset_provider,
    set_provider,
)

__all__ = [
    "Entitlements",
    "Tier",
    "UNLIMITED",
    "allow_targets",
    "cap_screens",
    "cap_tests",
    "entitlements",
    "has_feature",
    "reset_provider",
    "set_provider",
]
