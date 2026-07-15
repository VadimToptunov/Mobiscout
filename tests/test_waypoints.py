"""Waypoints: the crawler passes gates (login/OTP/permission/biometric) to reach
the screens behind them. Driven with a recording fake driver — device-free."""

from framework.crawler.app_crawler import AppCrawler, CrawlElement, CrawlScreen
from framework.crawler.waypoints import Waypoint, apply_first_match, matches


class RecordingDriver:
    """Records tap/type/back and serves a scripted sequence of page sources."""

    def __init__(self, pages):
        self._pages = list(pages)
        self._i = 0
        self.calls = []

    def page_source(self):
        return self._pages[min(self._i, len(self._pages) - 1)]

    def tap(self, x, y):
        self.calls.append(("tap", x, y))
        self._i = min(self._i + 1, len(self._pages) - 1)

    def type_text(self, text):
        self.calls.append(("type", text))

    def back(self):
        self.calls.append(("back",))

    def current_package(self):
        return "com.x"


def _el(cls, text="", rid="", desc=""):
    return CrawlElement(
        resource_id=rid,
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=True,
        bounds=(0, 0, 100, 40),
        package="com.x",
    )


def _login_screen():
    return CrawlScreen(
        "login",
        [
            _el("android.widget.EditText", rid="email", desc="Email"),
            _el("android.widget.EditText", rid="password", desc="Password"),
            _el("android.widget.Button", text="Sign in", rid="signin"),
        ],
        platform="android",
    )


def test_matches_by_text_and_input():
    s = _login_screen()
    assert matches(Waypoint(when={"text_contains": "sign in"}, action="fill"), s)
    assert matches(Waypoint(when={"has_input": True}, action="fill"), s)
    assert not matches(Waypoint(when={"text_contains": "checkout"}, action="fill"), s)


def test_fill_waypoint_types_credentials_and_taps_submit():
    driver = RecordingDriver(["<hierarchy/>"])
    wp = Waypoint(
        when={"text_contains": "sign in"},
        action="fill",
        data={"fields": {"email": "test@example.com", "password": "Pw123!"}, "submit": "Sign in"},
    )
    assert apply_first_match([wp], driver, _login_screen())
    typed = [c[1] for c in driver.calls if c[0] == "type"]
    assert "test@example.com" in typed and "Pw123!" in typed
    assert ("tap", 50, 20) in driver.calls  # submit tapped (element center)


def test_totp_waypoint_enters_current_code():
    otp_screen = CrawlScreen(
        "otp",
        [
            _el("android.widget.EditText", rid="otp", desc="One-time code"),
            _el("android.widget.Button", text="Verify", rid="verify"),
        ],
        platform="android",
    )
    driver = RecordingDriver(["<hierarchy/>"])
    wp = Waypoint(
        when={"text_contains": "one-time"},
        action="totp",
        data={"secret": "JBSWY3DPEHPK3PXP", "field": "otp", "submit": "Verify"},
    )
    assert apply_first_match([wp], driver, otp_screen)
    typed = [c[1] for c in driver.calls if c[0] == "type"]
    assert len(typed) == 1 and typed[0].isdigit() and len(typed[0]) == 6  # a TOTP code


def test_crawler_passes_gate_and_reaches_screen_behind():
    # Page 0: login (gate). After the waypoint taps submit, page 1: the home screen.
    login_xml = (
        '<hierarchy><node class="android.widget.EditText" resource-id="email" text="" '
        'content-desc="Email" clickable="true" bounds="[0,0][100,40]" package="com.x"/>'
        '<node class="android.widget.Button" resource-id="signin" text="Sign in" '
        'clickable="true" bounds="[0,50][100,90]" package="com.x"/></hierarchy>'
    )
    home_xml = (
        '<hierarchy><node class="android.widget.TextView" resource-id="welcome" text="Welcome home" '
        'clickable="false" bounds="[0,0][200,40]" package="com.x"/></hierarchy>'
    )
    driver = RecordingDriver([login_xml, home_xml])
    wp = Waypoint(
        when={"text_contains": "sign in"}, action="fill", data={"fields": {"email": "a@b.com"}, "submit": "Sign in"}
    )
    result = AppCrawler(driver, "com.x", max_steps=5, waypoints=[wp]).crawl()
    # The home screen (behind the gate) is now part of the crawl.
    assert any("welcome" in " ".join(e.resource_id for e in s.elements) for s in result.screens.values())
    assert any(c[0] == "type" for c in driver.calls)  # the gate was filled


def test_pipeline_run_kit_applies_config_waypoints(tmp_path, monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")
    from framework.crawler.pipeline import run_kit

    login_xml = (
        '<hierarchy><node class="android.widget.EditText" resource-id="email" content-desc="Email" '
        'clickable="true" bounds="[0,0][100,40]" package="com.x"/>'
        '<node class="android.widget.Button" resource-id="signin" text="Sign in" '
        'clickable="true" bounds="[0,50][100,90]" package="com.x"/></hierarchy>'
    )
    home_xml = (
        '<hierarchy><node class="android.widget.Button" resource-id="home" text="Home" '
        'clickable="true" bounds="[0,0][100,40]" package="com.x"/></hierarchy>'
    )
    driver = RecordingDriver([login_xml, home_xml])
    run_kit(
        {
            "package": "com.x",
            "targets": ["python_pytest"],
            "output": str(tmp_path),
            "waypoints": [
                {
                    "when": {"text_contains": "sign in"},
                    "action": "fill",
                    "data": {"fields": {"email": "a@b.com"}, "submit": "Sign in"},
                }
            ],
        },
        driver=driver,
    )
    assert any(c[0] == "type" for c in driver.calls)  # config waypoint -> gate filled
