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

import re
from typing import Iterable

from framework.crawler.models import CrawlElement

# Field hints that mark an input as holding a monetary amount / quantity. Single source of
# truth: _sample_value / _invalid_value fill such a field, and _is_money_screen uses it as
# field-level evidence that a screen involves money (so an amount input with no visible
# currency symbol still gates the ambiguous financial verbs — MC1).
_AMOUNT_FIELD_HINTS = ("amount", "qty", "quantity", "number", "count")


def _is_amount_field(element: CrawlElement) -> bool:
    """Whether this input holds a monetary amount / quantity, from its text/id/class. A
    phone/OTP field is explicitly excluded — "phone number" is not money, and blocking it
    would strand OTP-by-phone flows."""
    hint = f"{element.text} {element.content_desc} {element.resource_id} {element.class_name}".lower()
    if any(k in hint for k in ("phone", "tel", "mobile")):
        return False
    return any(k in hint for k in _AMOUNT_FIELD_HINTS)


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
    if _is_amount_field(element):
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
    if _is_amount_field(element):
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

# The money-moving / destructive submit verbs — the single source of truth folded into the
# crawler's DESTRUCTIVE_BLOCKLIST (app_crawler) and gated out of the codegen submit picker
# (graph). Two tiers, because matching a generic verb by itself over-blocks:
#
#  * _ALWAYS_FINANCIAL_LABELS — rarely benign, blocked whenever they appear.
#  * _CONTEXT_FINANCIAL_LABELS — "send"/"confirm"/"exchange" are usually innocent (OTP
#    "Send code", "Confirm email", a chat composer); only their money sense is destructive.
#    These are blocked ONLY on a screen that also shows a money field (see _is_money_screen),
#    so an OTP / messaging / confirmation flow is still crawled while "Send" on a transfer
#    form is not. All matching is on word boundaries so "send" never fires on "resend"/
#    "sender" and "pay" never on "PayPal"/"Payment".
_ALWAYS_FINANCIAL_LABELS = (
    "pay",
    "buy",
    "purchase",
    "checkout",
    "wire",
    "transfer",
)
_CONTEXT_FINANCIAL_LABELS = (
    "send",
    "confirm",
    "exchange",
)
_FINANCIAL_LABELS = _ALWAYS_FINANCIAL_LABELS + _CONTEXT_FINANCIAL_LABELS

# Signals that a screen involves money — a visible currency symbol, or an amount/account
# hint. Used to gate the ambiguous _CONTEXT_FINANCIAL_LABELS.
_MONEY_SYMBOLS = ("$", "€", "£", "¥", "₽")
_MONEY_HINTS = ("amount", "currency", "iban", "sort code", "account number", "recipient", "balance")


def _label_has_token(needle: str, label: str) -> bool:
    """True if ``needle`` occurs in ``label`` as a whole word/phrase (word-boundary match),
    so "send" doesn't fire on "resend"/"sender" nor "pay" on "PayPal"/"Payment". ``label``
    is expected lowercased; ``needle`` may be multi-word ("remove account")."""
    return re.search(r"\b" + re.escape(needle) + r"\b", label) is not None


def _is_money_screen(elements: Iterable[CrawlElement]) -> bool:
    """Whether the screen involves money. Consults FIELD-LEVEL evidence, not just visible
    label text (MC1): a visible currency symbol, an amount input detected from its id/type
    the same way _sample_value fills it (so a transfer form whose amount box shows no symbol
    or hint *word* is still recognised), or a money hint (currency/iban/recipient/…) anywhere
    in an element's text/id/class."""
    for e in elements:
        if any(sym in f"{e.text} {e.content_desc}" for sym in _MONEY_SYMBOLS):
            return True
        if _is_amount_field(e):
            return True
        hint = f"{e.text} {e.content_desc} {e.resource_id} {e.class_name}".lower()
        if any(h in hint for h in _MONEY_HINTS):
            return True
    return False
