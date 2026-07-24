"""Finding severity — the single canonical definition.

Supersedes the copies in ``security.types`` (``Severity``),
``analysis.security_analyzer`` (``SeverityLevel``) and
``security.advanced.base`` (``RiskLevel``). The plain-``Enum`` variants compared
unequal to their own string, which is exactly why ``severity == "critical"`` was
silently always-``False`` in the security CLI before #218.
"""

from enum import Enum


class Severity(str, Enum):
    """Severity of a security / quality finding, highest to lowest.

    ``str``-based so ``severity == "critical"`` holds and ``.value`` yields the
    wire string used in SARIF / JSON reports.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
