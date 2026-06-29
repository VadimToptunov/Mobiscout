"""
Shared security types.

A single canonical severity vocabulary. The SAST, DAST and OWASP scanners each
defined their own identical critical/high/medium/low/info enum (`Severity`,
`DASTSeverity`, `SeverityLevel`); those are now aliases of the one defined here,
so a "high" finding is the same object everywhere and there is one place to
extend the scale.

Note: supply_chain.VulnerabilitySeverity (uses UNKNOWN, not INFO) and
advanced_security.RiskLevel (integer-weighted) have different vocabularies and
are intentionally left separate.
"""

from __future__ import annotations

from enum import Enum


class Severity(Enum):
    """Canonical security finding severity.

    Plain Enum (not ``str, Enum``) to exactly preserve the behaviour of the
    three identical enums it replaces — equality and serialization semantics
    are unchanged; ``.value`` is the lowercase string.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
