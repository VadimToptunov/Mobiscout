"""
Shared form-value vocabulary — one source of truth for the values the crawler
types into forms *and* the values the codegen emits for generated tests.

Keeping these together fixes a class of desync bug: the live crawl and the
generated test must agree on what a field is filled with, or a positive test
types the wrong kind of data (e.g. "Test" into an amount field the crawl filled
with "10") and fails on a real device. Both :mod:`framework.crawler.app_crawler`
(the live crawl) and :mod:`framework.crawler.graph` (codegen) import from here.
"""

from __future__ import annotations

from framework.crawler.models import CrawlElement


def _sample_value(element: CrawlElement) -> str:
    """A realistic value for a form field, inferred from its label/id/class — so the
    crawl can *fill and submit* forms, not stall at the first text field, and the
    generated positive test types the same kind of data."""
    hint = f"{element.text} {element.content_desc} {element.resource_id} {element.class_name}".lower()
    if "email" in hint or "e-mail" in hint:
        return "test@example.com"
    if "secure" in hint or any(k in hint for k in ("password", "passwd", "pwd", "pass")):
        return "Password123!"
    if any(k in hint for k in ("phone", "tel", "mobile")):
        return "1234567890"
    if any(k in hint for k in ("amount", "qty", "quantity", "number", "count")):
        return "10"
    if "search" in hint or "query" in hint:
        return "test"
    if "name" in hint:
        return "Test User"
    return "Test"


def _invalid_value(element: CrawlElement) -> str:
    """A deliberately-invalid value for a form field, to exercise the *negative*
    (validation-error) branch. An empty string means "no strongly-typed rule
    matched, so there's no meaningful invalid value to type" — the caller skips
    the field rather than typing nothing."""
    hint = f"{element.text} {element.content_desc} {element.resource_id} {element.class_name}".lower()
    if "email" in hint or "e-mail" in hint:
        return "not-an-email"
    if "secure" in hint or any(k in hint for k in ("password", "passwd", "pwd", "pass")):
        return "1"  # too short to satisfy any real password policy
    if any(k in hint for k in ("phone", "tel", "mobile")):
        return "abc"  # letters where digits are required
    if any(k in hint for k in ("amount", "qty", "quantity", "number", "count")):
        return "-1"  # negative where a positive quantity is required
    return ""


# Button labels that submit a form — the control whose tap commits typed input.
# Used both to find the submit control during a crawl (to probe a form with invalid
# data) and to locate it in codegen. This list DOES include money-moving verbs
# (confirm/send/transfer/exchange) so an opted-in --allow-destructive crawl can reach
# the forms behind them — but a DEFAULT crawl never taps them, because those verbs are
# also in _FINANCIAL_LABELS below → the crawler's DESTRUCTIVE_BLOCKLIST.
_SUBMIT_LABELS = (
    "submit",
    "login",
    "log in",
    "sign in",
    "signin",
    "sign up",
    "signup",
    "register",
    "continue",
    "next",
    "confirm",
    "send",
    "save",
    "apply",
    "exchange",
    "transfer",
    "done",
)

# The money-moving / destructive subset of the submit verbs — the single source of truth
# folded into the crawler's DESTRUCTIVE_BLOCKLIST (app_crawler) and gated out of the codegen
# submit picker (graph). So neither a live negative probe nor a generated fuzz/negative case
# taps "Pay"/"Buy"/"Transfer"/"Send"/"Confirm" by default; they rely on the app's own
# validation only under an explicit --allow-destructive (a throwaway/sandbox build).
_FINANCIAL_LABELS = (
    "pay",
    "buy",
    "purchase",
    "checkout",
    "confirm",
    "transfer",
    "exchange",
    "send",
    "wire",
)
