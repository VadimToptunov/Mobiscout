"""Feature gating for the optional / PRO CLI lanes (audit §2026-08 §6 scope).

Mobiscout's free core is the **crawl → test-kit** path. The secondary analysis lanes —
security scanning, accessibility auditing, fuzzing, load testing/profiling — are real and
stay in the repo, but they are *optional* PRO-candidate features, not part of the free 1.0
pitch. This module marks that boundary.

The gate is a **no-op on the open-core engine**: the default UNLIMITED entitlements grant
every feature, so these commands run exactly as before. It only bites when a PRO provider
installs limits via :func:`framework.licensing.set_provider` — then a tier without the
feature gets a clear upsell instead of the command.
"""

from __future__ import annotations

import click

from framework.licensing import has_feature

#: The optional-lane feature flags, so the PRO tier definition and the docs share one
#: source of truth for what lives outside the free core.
SECURITY_SCAN = "security_scan"
A11Y_AUDIT = "a11y_audit"
FUZZING = "fuzzing"
LOAD_TESTING = "load_testing"
CLOUD_GRID = "cloud_grid"

PRO_LANE_FEATURES = (SECURITY_SCAN, A11Y_AUDIT, FUZZING, LOAD_TESTING, CLOUD_GRID)


def require_feature(feature: str, label: str) -> None:
    """Abort with an upsell when ``feature`` isn't entitled. A no-op on the open-core
    engine (UNLIMITED grants everything); enforced only under a limited PRO provider."""
    if not has_feature(feature):
        raise click.ClickException(
            f"{label} is a Mobiscout PRO feature and isn't enabled on this tier. "
            "The free tier covers the crawl → test-kit path; upgrade to unlock this lane."
        )
