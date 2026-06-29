"""Pins the security severity-enum consolidation."""

from framework.security.dast_analyzer import DASTSeverity
from framework.security.sast_analyzer import Severity
from framework.security.scanner import SeverityLevel
from framework.security.types import Severity as Canonical


def test_three_severity_enums_are_one_canonical_object():
    assert Severity is Canonical
    assert DASTSeverity is Canonical
    assert SeverityLevel is Canonical


def test_values_unchanged():
    # Behaviour-preserving: same lowercase string values as before the merge.
    assert [s.value for s in Canonical] == ["critical", "high", "medium", "low", "info"]
