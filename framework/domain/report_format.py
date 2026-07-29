"""Report output format — the single canonical definition.

Supersedes the three divergent copies that used to live in
``reporting.unified_reporter`` (``HTML/ALLURE/JUNIT/JSON``),
``reporting.base_reporter`` (``JSON/HTML/TEXT/XML/MARKDOWN``) and
``reporting.report_generator`` (``HTML/PDF/MARKDOWN/JSON``). Because each
subsystem declared its own enum, a ``ReportFormat.HTML`` from one module
compared *unequal* to the ``ReportFormat.HTML`` of another, and no single value
covered every supported format.

This is the union of all three, so every former member still resolves, and —
like the other domain value objects — it is a ``str``-based ``Enum`` so that
``ReportFormat.HTML == "html"`` holds and ``.value`` still yields the wire
string. The old modules re-export this object, so existing imports keep working
and all instances now share identity.
"""

from enum import Enum


class ReportFormat(str, Enum):
    """A supported report output format (union of every subsystem's formats)."""

    HTML = "html"
    JSON = "json"
    MARKDOWN = "markdown"
    ALLURE = "allure"
    JUNIT = "junit"
    TEXT = "text"
    XML = "xml"
    PDF = "pdf"
