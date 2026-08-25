"""Built-in obstacle handling (device-free):

* unit — the matchers/actions dismiss the right control and don't fire on real
  content; terminal dead-ends are named; and
* integration — a re-appearing login is re-authed (bounded), and a terminal
  obstacle (paywall) is mapped but never tapped into.
"""

from framework.crawler.app_crawler import AppCrawler, parse_screen
from framework.crawler.obstacles import clear_obstacle, terminal_obstacle
from framework.crawler.waypoints import Waypoint

APP = "com.example.app"


def _n(text, bounds, cls="android.widget.Button"):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="{cls}" resource-id="" text="{text}" content-desc="" '
        f'clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _screen(*nodes):
    return parse_screen('<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>")


class _Rec:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))


# --- unit: non-terminal clearing -------------------------------------------------


def test_consent_declines_privacy_first():
    scr = _screen(
        _n("We use cookies to improve your experience", (0, 0, 300, 40)),
        _n("Reject all", (0, 50, 150, 90)),
        _n("Accept all", (160, 50, 300, 90)),
    )
    d = _Rec()
    assert clear_obstacle(d, scr) == "consent"
    assert d.taps == [(75, 70)]  # tapped "Reject all", not "Accept all"


def test_consent_accepts_only_when_no_decline():
    scr = _screen(_n("This site uses cookies", (0, 0, 300, 40)), _n("Accept all", (0, 50, 150, 90)))
    d = _Rec()
    assert clear_obstacle(d, scr) == "consent"
    assert d.taps == [(75, 70)]


def test_onboarding_taps_skip():
    scr = _screen(_n("Welcome — take a quick tour", (0, 0, 300, 40)), _n("Skip", (240, 0, 300, 40)))
    d = _Rec()
    assert clear_obstacle(d, scr) == "onboarding"
    assert d.taps == [(270, 20)]


def test_onboarding_does_not_fire_done_on_welcome_content():
    # A real content screen that merely says "Welcome back" and has a "Done" button (a
    # form/date-picker Done) must NOT be treated as onboarding — "done" is not a skip.
    scr = _screen(_n("Welcome back, Sam", (0, 0, 300, 40)), _n("Done", (240, 0, 300, 40)))
    d = _Rec()
    assert clear_obstacle(d, scr) is None
    assert d.taps == []


def test_nag_dismissed():
    scr = _screen(_n("Enjoying the app? Rate us!", (0, 0, 300, 40)), _n("Not now", (0, 50, 150, 90)))
    d = _Rec()
    assert clear_obstacle(d, scr) == "nag"
    assert d.taps == [(75, 70)]


def test_no_false_positive_on_real_content():
    scr = _screen(_n("Account balance", (0, 0, 300, 40)), _n("Transfer", (0, 50, 150, 90)))
    d = _Rec()
    assert clear_obstacle(d, scr) is None
    assert d.taps == []


def test_blocking_dialog_never_taps_dont_allow():
    # A system permission dialog: "Don't allow" contains "allow" (a SAFE label), but
    # tapping it denies the permission. _clear_blocking_dialog must tap the affirmative
    # "Allow", never the negated one.
    perm_xml = (
        '<hierarchy rotation="0">'
        + _n("Don't allow", (0, 0, 100, 40))
        + _n("Allow", (0, 100, 100, 140))
        + "</hierarchy>"
    )

    class _D:
        def __init__(self):
            self.tapped = None

        def page_source(self):
            return perm_xml

        def tap(self, x, y):
            self.tapped = (x, y)

        def current_package(self):
            return APP

    d = _D()
    assert AppCrawler(d, APP)._clear_blocking_dialog() is True
    assert d.tapped == (50, 120)  # center of "Allow", never "Don't allow" (50, 20)


# --- unit: terminal dead-ends ----------------------------------------------------


def test_terminal_obstacles_named():
    assert terminal_obstacle(_screen(_n("Please verify you are human", (0, 0, 300, 40)))) == "captcha"
    assert terminal_obstacle(_screen(_n("Update required to continue", (0, 0, 300, 40)))) == "update_wall"
    assert terminal_obstacle(_screen(_n("Start free trial — $9.99 per month", (0, 0, 300, 40)))) == "paywall"
    assert terminal_obstacle(_screen(_n("Home", (0, 0, 300, 40)), _n("Settings", (0, 50, 100, 90)))) is None


# --- integration: re-auth (bounded re-fire) --------------------------------------


class _ReAuthDriver:
    """login (input + Log in) -> home (Reload). Tapping Reload expires the session
    and drops back on the same login screen — the crawler must re-auth."""

    def __init__(self):
        self.state = "login"
        self.pkg = APP
        self.fills = 0
        self.nav = []

    def page_source(self):
        if self.state == "login":
            return (
                '<hierarchy rotation="0">'
                + _n("Username", (0, 0, 200, 40), cls="android.widget.EditText")
                + _n("Log in", (0, 50, 100, 90))
                + "</hierarchy>"
            )
        return '<hierarchy rotation="0">' + _n("Reload", (0, 0, 100, 40)) + "</hierarchy>"

    def current_package(self):
        return self.pkg

    def back(self):
        if self.nav:
            self.state = self.nav.pop()

    def _label_at(self, x, y):
        for e in parse_screen(self.page_source()).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                return e.label
        return ""

    def type_text(self, text):
        self.fills += 1

    def tap(self, x, y):
        label = self._label_at(x, y).lower()
        if self.state == "login" and label == "log in":
            self.nav.append("login")
            self.state = "home"
        elif self.state == "home" and label == "reload":
            self.state = "login"  # session expired -> back to the (same) login screen


def test_reauth_refires_login_on_session_expiry():
    driver = _ReAuthDriver()
    wp = Waypoint(when={"has_input": True}, action="fill", data={"fields": {"user": "demo"}, "submit": "log in"})
    AppCrawler(driver, APP, max_steps=30, waypoints=[wp]).crawl()
    # Filled at least twice: the initial login + at least one re-auth after the
    # session dropped us back on the login screen.
    assert driver.fills >= 2


def _nid(text, bounds, rid, cls="android.widget.Button", clickable="true"):
    """A node with a resource-id, so structurally-similar screens get distinct
    fingerprints (the fingerprint ignores text, which is dynamic)."""
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="{cls}" resource-id="{rid}" text="{text}" content-desc="" '
        f'clickable="{clickable}" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


class _MidGateDriver:
    """home (Secure area) -> login gate (input + Sign in) -> secure (Open details)
    -> details. The gate appears MID-crawl (after a tap), so this exercises the
    behind-gate *exploration* path, not the entry gate."""

    _PAGES = {
        "home": _nid("Secure area", (0, 0, 200, 40), "btn_secure"),
        "login": (
            _nid("", (0, 0, 200, 40), "email", cls="android.widget.EditText")
            + _nid("Sign in", (0, 50, 100, 90), "btn_signin")
        ),
        "secure": _nid("Open details", (0, 0, 200, 40), "btn_details"),
        "details": _nid(
            "Detail body", (0, 0, 200, 40), "detail_body", cls="android.widget.TextView", clickable="false"
        ),
    }

    def __init__(self):
        self.state = "home"
        self.nav = []

    def page_source(self):
        return '<hierarchy rotation="0">' + self._PAGES[self.state] + "</hierarchy>"

    def current_package(self):
        return APP

    def back(self):
        if self.nav:
            self.state = self.nav.pop()

    def _label_at(self, x, y):
        for e in parse_screen(self.page_source()).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                return e.label.lower()
        return ""

    def type_text(self, text):
        pass

    def tap(self, x, y):
        label = self._label_at(x, y)
        moves = {
            ("home", "secure area"): "login",
            ("login", "sign in"): "secure",
            ("secure", "open details"): "details",
        }
        nxt = moves.get((self.state, label))
        if nxt:
            self.nav.append(self.state)
            self.state = nxt


def test_crawler_explores_behind_a_mid_crawl_gate():
    # Regression for the setdefault-before-explore bug: a gate encountered mid-crawl had
    # its behind-screen recorded then immediately treated as "already seen", so the whole
    # post-auth area was mapped as one unexplored node. "Detail body" is reachable ONLY by
    # exploring the screen BEHIND the gate, so its presence proves exploration happened.
    driver = _MidGateDriver()
    wp = Waypoint(when={"has_input": True}, action="fill", data={"fields": {"email": "a@b.com"}, "submit": "sign in"})
    result = AppCrawler(driver, APP, max_steps=40, waypoints=[wp]).crawl()
    labels = {e.label for s in result.screens.values() for e in s.elements}
    assert "Detail body" in labels


# --- integration: terminal obstacle mapped but not explored ----------------------


class _PaywallDriver:
    """home (Go) -> paywall. The paywall's only control must never be tapped."""

    def __init__(self):
        self.state = "home"
        self.pkg = APP
        self.tapped_labels = []
        self.nav = []

    def page_source(self):
        if self.state == "home":
            return '<hierarchy rotation="0">' + _n("Go", (0, 0, 100, 40)) + "</hierarchy>"
        return (
            '<hierarchy rotation="0">'
            + _n("Start your free trial for $4.99 per month", (0, 0, 300, 40))
            + _n("Continue to app", (0, 50, 200, 90))
            + "</hierarchy>"
        )

    def current_package(self):
        return self.pkg

    def back(self):
        if self.nav:
            self.state = self.nav.pop()

    def _label_at(self, x, y):
        for e in parse_screen(self.page_source()).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                return e.label
        return ""

    def tap(self, x, y):
        label = self._label_at(x, y)
        self.tapped_labels.append(label)
        if self.state == "home" and label == "Go":
            self.nav.append("home")
            self.state = "paywall"


def test_terminal_paywall_mapped_but_not_tapped():
    driver = _PaywallDriver()
    result = AppCrawler(driver, APP, max_steps=30).crawl()
    # The paywall screen is in the map...
    blobs = [" ".join(e.label for e in s.elements).lower() for s in result.screens.values()]
    assert any("per month" in b for b in blobs)
    # ...but its control was never tapped (we backed out instead of poking it).
    assert "Continue to app" not in driver.tapped_labels
