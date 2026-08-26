"""Unit tests for sandbox mode (`allow_destructive`) — letting a crawl of a
throwaway test app tap destructive/financial actions to go deeper, while still
never ending the session."""

from framework.crawler.app_crawler import (
    DEFAULT_BLOCKLIST,
    DESTRUCTIVE_BLOCKLIST,
    SESSION_BLOCKLIST,
    AppCrawler,
    parse_screen,
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


# --- the gate as the crawl loop actually uses it ------------------------------
# Everything above tests the predicate in isolation. These drive the REAL crawl
# loop over a fake app, because the predicate being right is worthless if the loop
# forgets to pass money_context: with the wiring gone, a default crawl taps "Send"
# on a transfer form — a real money move — and every pure-predicate test above
# still passes.


def _button(label, rid, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.Button" resource-id="{rid}" text="{label}" '
        f'content-desc="" clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _amount_input(rid, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.EditText" resource-id="{rid}" text="" '
        f'content-desc="" clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _label(text, bounds):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="android.widget.TextView" resource-id="" text="{text}" '
        f'content-desc="" clickable="false" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _screen(*nodes):
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


# home     -- "Send code" --> otp        (no money field: "Send code" must be tapped)
#          -- "Move money" --> transfer  (amount field: "Send" must NOT be tapped)
#          -- "Wallet" --> wallet        (amount field only BELOW the fold)
SCREENS = {
    "home": _screen(
        _button("Send code", "com.x:id/otp", (0, 0, 100, 50)),
        _button("Move money", "com.x:id/nav_send", (0, 60, 100, 110)),
        _button("Wallet", "com.x:id/nav_wallet", (0, 120, 100, 170)),
    ),
    "otp": _screen(_label("Code sent", (0, 0, 100, 50))),
    "transfer": _screen(
        _amount_input("com.x:id/amount_field", (0, 0, 100, 50)),
        _button("Send", "com.x:id/submit", (0, 60, 100, 110)),
        _button("Add note", "com.x:id/note", (0, 120, 100, 170)),
    ),
    "note": _screen(_label("Note", (0, 0, 100, 50))),
    "sent": _screen(_label("Money sent", (0, 0, 100, 50))),  # only reachable by tapping Send
    # The wallet's amount field is off-screen until a scroll reveals it, so the
    # frame starts non-money and must re-arm (sticky) once the fold is opened.
    "wallet": _screen(_label("Wallet", (0, 0, 100, 50))),
    "wallet_scrolled": _screen(
        _amount_input("com.x:id/amount_field", (0, 0, 100, 50)),
        _button("Send", "com.x:id/wallet_submit", (0, 60, 100, 110)),
    ),
}
TRANSITIONS = {
    ("home", "Send code"): "otp",
    ("home", "Move money"): "transfer",
    ("home", "Wallet"): "wallet",
    ("transfer", "Send"): "sent",
    ("transfer", "Add note"): "note",
    ("wallet", "Send"): "sent",
}


class _FakeApp:
    """Serves the fake app above and records every tapped label. ``scrolls`` maps a
    screen to the variant shown after the crawler scrolls it."""

    def __init__(self, start="home", scrolls=None):
        self.current = start
        self.scrolls = scrolls or {}
        self.scrolled = set()
        self.nav = []
        self.tapped_labels = []

    def _visible(self):
        name = self.current
        return SCREENS[self.scrolls[name] if name in self.scrolled else name]

    def page_source(self):
        return self._visible()

    def current_package(self):
        return APP

    def back(self):
        if self.nav:
            self.current = self.nav.pop()

    def scroll(self, direction="down"):
        if direction == "down" and self.current in self.scrolls:
            self.scrolled.add(self.current)

    def type_text(self, text):
        pass

    def tap(self, x, y):
        label = ""
        for e in parse_screen(self._visible()).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                label = e.label
                break
        self.tapped_labels.append(label)
        target = TRANSITIONS.get((self.current, label))
        if target:
            self.nav.append(self.current)
            self.current = target


def _crawl(driver, **kw):
    AppCrawler(driver, APP, max_steps=200, **kw).crawl()
    return driver.tapped_labels


def test_crawl_loop_never_taps_send_on_a_money_screen():
    tapped = _crawl(_FakeApp())
    assert "Send" not in tapped  # the transfer form's submit — a real money move
    assert "Send code" in tapped  # ...while the OTP screen's Send stays crawlable
    assert "Add note" in tapped  # and the money screen itself is still explored


def test_allow_destructive_lets_the_crawl_loop_reach_the_money_submit():
    tapped = _crawl(_FakeApp(), allow_destructive=True)
    assert "Send" in tapped


def test_crawl_loop_gates_send_on_a_money_screen_it_started_on():
    # Entry-screen wiring (root_money): a crawl that *starts* on the transfer form
    # has no parent frame to inherit the money flag from.
    tapped = _crawl(_FakeApp(start="transfer"))
    assert "Send" not in tapped
    assert "Add note" in tapped


def test_money_flag_re_arms_when_a_scroll_reveals_the_amount_field():
    # The amount field is below the fold, so the frame is created non-money; the
    # scroll that reveals it — and the "Send" beside it — must make the frame
    # sticky-money. Started on the wallet so only the scroll can arm the flag.
    tapped = _crawl(_FakeApp(start="wallet", scrolls={"wallet": "wallet_scrolled"}))
    assert tapped  # the scroll did reveal the below-the-fold controls
    assert "Send" not in tapped


# --- the tab-section wiring of the same gate ----------------------------------------
#
# A tab-based app takes a different path into the depth-first loop: _explore_tabs drives
# each section from its tab and passes root_money=self._money_screen(section). That is a
# sixth wiring point of the money gate, and the tests above cannot reach it — their
# fixture is android.widget.*, so _is_primary_nav is never true and _explore_tabs never
# runs. Without this test, deleting that root_money argument leaves the whole suite green
# while a default crawl taps Send on a tab whose root is a transfer form.

_TAB_W, _TAB_BOTTOM = 100, 800


def _ios(itype, name, x, y, w=100, h=40):
    return (
        f'<XCUIElementType{itype} type="XCUIElementType{itype}" name="{name}" '
        f'label="{name}" x="{x}" y="{y}" width="{w}" height="{h}" '
        f'visible="true" enabled="true"/>'
    )


_TAB_BAR = "".join(_ios("Button", n, i * _TAB_W, _TAB_BOTTOM) for i, n in enumerate(("Home", "Wallet", "More")))

# The Wallet tab's ROOT is itself a money screen: an amount field plus Send. Nothing
# above it in the stack can supply the money flag — only root_money can.
_TAB_SCREENS = {
    "home": [_ios("Button", "Overview", 0, 100)],
    "wallet": [
        _ios("TextField", "Amount", 0, 100),
        _ios("StaticText", "$120.00", 0, 160),
        _ios("Button", "Send", 0, 220),
        _ios("Button", "Add note", 0, 280),
    ],
    "more": [_ios("Button", "Settings", 0, 100)],
}


class _TabApp:
    """Three tabs; tapping a tab name switches section. Records tapped labels."""

    def __init__(self):
        self.current = "home"
        self.tapped_labels = []

    def _page(self):
        body = "".join(_TAB_SCREENS[self.current]) + _TAB_BAR
        return f'<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="TabApp">{body}</XCUIElementTypeApplication>'

    def page_source(self):
        return self._page()

    def current_package(self):
        return APP

    def back(self):
        pass  # tabs are switched by tapping the bar, not by Back

    def type_text(self, text):
        pass

    def tap(self, x, y):
        label = ""
        for e in parse_screen(self._page()).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                label = e.label
                break
        self.tapped_labels.append(label)
        if label.lower() in _TAB_SCREENS:
            self.current = label.lower()


def test_crawl_never_taps_send_on_a_tab_whose_root_is_a_money_screen():
    driver = _TabApp()
    AppCrawler(driver, APP, max_steps=200).crawl()
    tapped = driver.tapped_labels
    assert "Wallet" in tapped  # the tab section was actually reached...
    assert "Add note" in tapped  # ...and explored
    assert "Send" not in tapped  # ...but its money submit was never tapped


def test_allow_destructive_reaches_the_send_on_a_money_tab_root():
    driver = _TabApp()
    AppCrawler(driver, APP, max_steps=200, allow_destructive=True).crawl()
    assert "Send" in driver.tapped_labels
