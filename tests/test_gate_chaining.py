"""Gate chaining (device-free): a login that reveals an OTP that reveals the app
is passed as a *sequence* — each gate by its own waypoint — instead of handing a
revealed gate to normal exploration (which would type junk into it)."""

from framework.crawler.app_crawler import AppCrawler, parse_screen
from framework.crawler.waypoints import Waypoint

APP = "com.example.app"


def _n(text, bounds, cls="android.widget.Button"):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="{cls}" resource-id="" text="{text}" content-desc="" '
        f'clickable="true" bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _xml(*nodes):
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


class _ChainDriver:
    """login (input + Log in) -> otp (input + Verify) -> home. Each submit advances."""

    _SCREENS = {
        "login": _xml(_n("Username", (0, 0, 200, 40), cls="android.widget.EditText"), _n("Log in", (0, 50, 100, 90))),
        "otp": _xml(
            _n("Enter the code", (0, 0, 200, 30)),
            _n("code", (0, 40, 200, 80), cls="android.widget.EditText"),
            _n("Verify", (0, 90, 100, 130)),
        ),
        "home": _xml(_n("Welcome to your account", (0, 0, 200, 40))),
    }

    def __init__(self):
        self.state = "login"
        self.typed = []

    def page_source(self):
        return self._SCREENS[self.state]

    def current_package(self):
        return APP

    def back(self):
        pass

    def type_text(self, text):
        self.typed.append(text)

    def _label_at(self, x, y):
        for e in parse_screen(self.page_source()).elements:
            x1, y1, x2, y2 = e.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                return e.label
        return ""

    def tap(self, x, y):
        label = self._label_at(x, y).lower()
        if self.state == "login" and label == "log in":
            self.state = "otp"
        elif self.state == "otp" and label == "verify":
            self.state = "home"


def test_pass_gates_chains_login_then_otp():
    driver = _ChainDriver()
    crawler = AppCrawler(
        driver,
        APP,
        waypoints=[
            # OTP first (specific), login second (general) — apply_first_match order.
            Waypoint(when={"text_contains": "enter the code"}, action="fill",
                     data={"fields": {"code": "424242"}, "submit": "verify"}),
            Waypoint(when={"has_input": True}, action="fill",
                     data={"fields": {"user": "demo"}, "submit": "log in"}),
        ],
    )
    login = parse_screen(driver.page_source())
    assert crawler._pass_gates(login) is True
    # Chained through BOTH gates to the app — not stranded on the OTP screen.
    assert driver.state == "home"
    # The OTP field got the real code, not a sample value.
    assert "424242" in driver.typed


def test_pass_gates_no_waypoints_is_false():
    driver = _ChainDriver()
    crawler = AppCrawler(driver, APP)
    assert crawler._pass_gates(parse_screen(driver.page_source())) is False
    assert driver.state == "login"
