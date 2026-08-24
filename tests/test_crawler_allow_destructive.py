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


def test_default_blocks_financial_submit_verbs():
    # CS1: transfer/send/exchange and a bare "Confirm" are submit labels (so an opted-in
    # crawl can reach the forms behind them), but a DEFAULT crawl must never tap them — the
    # negative probe fills invalid data and would commit a money move, relying on the app's
    # own validation, which is exactly what the blocklist exists to not assume.
    c = _crawler()
    for label in ("Transfer", "Send money", "Exchange", "Confirm"):
        assert c._blocked(_el(label)), label
    # Ordinary, non-financial submit verbs stay crawlable.
    assert not c._blocked(_el("Continue"))
    assert not c._blocked(_el("Log in"))
    assert not c._blocked(_el("Save"))


def test_allow_destructive_reaches_financial_submits():
    # The escape hatch for a throwaway/sandbox app: --allow-destructive lifts the financial
    # block so the crawler can go past a "Send"/"Transfer"/"Confirm".
    c = _crawler(allow_destructive=True)
    for label in ("Transfer", "Send money", "Confirm"):
        assert not c._blocked(_el(label)), label


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
