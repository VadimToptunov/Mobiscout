"""Unit tests for sandbox mode (`allow_destructive`) — letting a crawl of a
throwaway test app tap destructive/financial actions to go deeper, while still
never ending the session."""

from framework.crawler.app_crawler import (
    DEFAULT_BLOCKLIST,
    DESTRUCTIVE_BLOCKLIST,
    SESSION_BLOCKLIST,
    AppCrawler,
)
from framework.crawler.models import CrawlElement

APP = "com.example.app"


class _NullDriver:
    def current_package(self):
        return APP


def _el(text):
    return CrawlElement(
        resource_id="",
        text=text,
        content_desc="",
        class_name="android.widget.Button",
        clickable=True,
        bounds=(0, 0, 100, 40),
        package="",
    )


def _crawler(**kw):
    return AppCrawler(_NullDriver(), APP, **kw)


def test_default_blocks_destructive_and_session():
    c = _crawler()
    assert c._blocked(_el("Pay now"))
    assert c._blocked(_el("Delete account"))
    assert c._blocked(_el("Log out"))
    assert not c._blocked(_el("Continue"))


def test_allow_destructive_unblocks_financial_but_not_logout():
    c = _crawler(allow_destructive=True)
    # Destructive/financial actions are now tappable...
    assert not c._blocked(_el("Pay now"))
    assert not c._blocked(_el("Buy"))
    assert not c._blocked(_el("Delete account"))
    assert not c._blocked(_el("Confirm order"))
    # ...but ending the session is still blocked (it only strands the crawl).
    assert c._blocked(_el("Log out"))
    assert c._blocked(_el("Sign out"))


def test_default_blocks_always_financial_verbs():
    # CS1: the unambiguous money verbs are blocked whenever they appear (money screen or
    # not) — the negative probe would fill invalid data and commit a real money move.
    c = _crawler()
    for label in ("Pay now", "Buy", "Purchase", "Checkout", "Wire funds", "Transfer"):
        assert c._blocked(_el(label)), label
    # Ordinary, non-financial submit verbs stay crawlable.
    assert not c._blocked(_el("Continue"))
    assert not c._blocked(_el("Log in"))
    assert not c._blocked(_el("Save"))


def test_context_financial_verbs_block_only_on_a_money_screen():
    # CR1: send/confirm/exchange are benign in most apps (OTP "Send code", "Confirm email",
    # a chat composer), so a default crawl blocks them ONLY when the screen shows a money
    # field — otherwise the OTP/messaging/confirmation flows become dead-ends.
    c = _crawler()
    for label in ("Send code", "Resend OTP", "Send message", "Confirm email", "Confirm", "Exchange rate"):
        assert not c._blocked(_el(label)), label  # no money context on the screen
    for label in ("Send", "Confirm", "Exchange"):
        assert c._blocked(_el(label), money_context=True), label  # e.g. a transfer form


def test_money_screen_detects_amount_field_by_id_without_a_currency_symbol():
    # MC1: a transfer form whose amount input is recognisable only from its id
    # (…/amount_field) — no visible currency symbol or hint *word* in the labels — must
    # still be a money screen (so its "Send" is blocked). An OTP screen (a code input) and a
    # phone field (phone-OTP) must NOT be, or those flows become dead-ends again.
    from framework.crawler.form_values import _is_money_screen

    def _field(rid):
        return CrawlElement(
            resource_id=rid,
            text="",
            content_desc="",
            class_name="android.widget.EditText",
            clickable=True,
            bounds=(0, 0, 100, 40),
            package="",
        )

    assert _is_money_screen([_el("To"), _field("com.x:id/amount_field"), _el("Send")])
    assert not _is_money_screen([_el("Code"), _field("com.x:id/otp_code"), _el("Send code")])
    assert not _is_money_screen([_field("com.x:id/phone_number"), _el("Send code")])


def test_blocklist_matches_whole_words_not_substrings():
    # CR1(a): word-boundary matching — "pay" must not fire on "PayPal"/"Payment", "buy" not
    # on "Buyer", "send" not on "resend"/"sender" (the latter two pre-existed #469).
    c = _crawler()
    for label in ("PayPal", "Payment methods", "Buyer details", "Resend", "Sender name"):
        assert not c._blocked(_el(label)), label


def test_allow_destructive_reaches_financial_submits():
    # The escape hatch for a throwaway/sandbox app: --allow-destructive lifts the financial
    # block so the crawler can go past a "Send"/"Transfer"/"Confirm" — even on a money screen.
    c = _crawler(allow_destructive=True)
    for label in ("Transfer", "Send money", "Confirm", "Pay now"):
        assert not c._blocked(_el(label), money_context=True), label


def test_explicit_blocklist_overrides_allow_destructive():
    c = _crawler(blocklist=("frobnicate",), allow_destructive=True)
    assert c._blocked(_el("Frobnicate this"))
    assert not c._blocked(_el("Pay now"))  # not in the explicit list
    assert not c._blocked(_el("Log out"))  # explicit list fully replaces the defaults


def test_blocklist_constants_compose():
    assert DEFAULT_BLOCKLIST == SESSION_BLOCKLIST + DESTRUCTIVE_BLOCKLIST
    assert "logout" in SESSION_BLOCKLIST
    assert "pay" in DESTRUCTIVE_BLOCKLIST
    assert not set(SESSION_BLOCKLIST) & set(DESTRUCTIVE_BLOCKLIST)  # disjoint tiers
