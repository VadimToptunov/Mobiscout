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
